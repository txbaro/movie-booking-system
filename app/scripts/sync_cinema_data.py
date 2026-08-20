import argparse
import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.collectors.cinestar import CinestarCollector
from app.collectors.fixture import FixtureCollector
from app.collectors.galaxy import GalaxyCollector
from app.collectors.lotte import LotteCollector
from app.core.database import AsyncSessionLocal, engine
from app.services.cinema_sync import sync_collected_showtimes, sync_collector
from app.services.redis_features import distributed_lock


FIXTURE_SOURCES = {
    "fixture": ("fixture", Path("app/fixtures/sample_showtimes.json")),
    "mock-cgv": ("cgv", Path("app/fixtures/providers/cgv_showtimes.json")),
    "mock-galaxy": (
        "galaxy",
        Path("app/fixtures/providers/galaxy_showtimes.json"),
    ),
    "mock-cinestar": (
        "cinestar",
        Path("app/fixtures/providers/cinestar_showtimes.json"),
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronize cinema schedule data")
    parser.add_argument(
        "--source",
        choices=[*FIXTURE_SOURCES, "demo", "cinestar", "lotte", "galaxy"],
        default="fixture",
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date(),
        help="Ngày YYYY-MM-DD; mặc định là hôm nay theo giờ Việt Nam",
    )
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=None,
        help="Override fixture path; only valid for a single source",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Số ngày liên tiếp; collector live mặc định 7, fixture mặc định 1",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.source == "demo":
        if args.fixture_path is not None:
            raise SystemExit("--fixture-path không dùng được với --source demo")
        sources = ["mock-cgv", "mock-galaxy", "mock-cinestar"]
    else:
        sources = [args.source]

    results = {}
    async with AsyncSessionLocal() as db:
        for source in sources:
            lock_source = (
                source
                if source in {"cinestar", "lotte", "galaxy"}
                else FIXTURE_SOURCES[source][0]
            )
            async with distributed_lock(f"collector:{lock_source}") as acquired:
                if not acquired:
                    results[lock_source] = {
                        "status": "skipped",
                        "reason": "collector_already_running",
                    }
                    continue
                if source in {"cinestar", "lotte", "galaxy"}:
                    if args.fixture_path is not None:
                        raise SystemExit(
                            f"--fixture-path không dùng được với --source {source}"
                        )
                    collectors = {
                        "cinestar": CinestarCollector,
                        "lotte": LotteCollector,
                        "galaxy": GalaxyCollector,
                    }
                    collector = collectors[source]()
                    collector_source = collector.source
                    days = args.days if args.days is not None else 7
                    if not 1 <= days <= 31:
                        raise SystemExit("--days phải nằm trong khoảng 1..31")
                    items = await collector.collect_range(args.date, days)
                    result = await sync_collected_showtimes(
                        db, collector_source, items
                    )
                else:
                    if args.days not in (None, 1):
                        raise SystemExit("--days > 1 chỉ hỗ trợ collector live")
                    collector_source, default_path = FIXTURE_SOURCES[source]
                    path = args.fixture_path or default_path
                    collector = FixtureCollector(path, source=collector_source)
                    result = await sync_collector(db, collector, args.date)
                results[collector_source] = result.model_dump()

    if len(results) == 1:
        print(json.dumps(next(iter(results.values())), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
