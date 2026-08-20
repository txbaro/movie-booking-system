from datetime import date
from pathlib import Path

import httpx
import pytest

from app.collectors.galaxy import GalaxyCollector, GalaxyCollectorError

FIXTURES = Path(__file__).parent / "fixtures"


def _schedule_html() -> str:
    payload = (FIXTURES / "galaxy_schedule.json").read_text(encoding="utf-8")
    return (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        f"{payload}</script></html>"
    )


def test_parse_next_data_into_normalized_showtime():
    items = GalaxyCollector.parse_schedule_page(
        _schedule_html(), {date(2026, 8, 20)}
    )

    assert len(items) == 1
    item = items[0]
    assert item.external_id == "1001-257743"
    assert item.movie.external_id == "movie-1"
    assert item.movie.poster_url == "https://cdn.example/poster.jpg"
    assert item.cinema.external_id == "cinema-1"
    assert item.cinema.city == "TP Hồ Chí Minh"
    assert str(item.cinema.latitude) == "10.773390"
    assert item.start_time.isoformat() == "2026-08-20T14:15:00+07:00"
    assert item.format == "2D Phụ Đề"
    assert item.language == "Phụ đề"
    assert item.external_booking_url == (
        "https://www.galaxycine.vn/booking/phim-galaxy?sessionId=1001-257743"
    )


@pytest.mark.asyncio
async def test_collect_range_fetches_schedule_page_once():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=_schedule_html())

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://galaxy.test"
    ) as client:
        collector = GalaxyCollector(
            base_url="https://galaxy.test",
            client=client,
            request_interval_seconds=0,
        )
        items = await collector.collect_range(date(2026, 8, 20), days=2)

    assert len(items) == 2
    assert len(requests) == 1
    assert requests[0].url.path == "/lich-chieu/"


@pytest.mark.asyncio
async def test_redirect_has_clear_antibot_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": str(request.url)})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://galaxy.test"
    ) as client:
        collector = GalaxyCollector(
            base_url="https://galaxy.test",
            client=client,
            request_interval_seconds=0,
        )
        with pytest.raises(GalaxyCollectorError, match="GALAXY_COOKIE"):
            await collector.collect(date(2026, 8, 20))


@pytest.mark.asyncio
async def test_collect_range_rejects_unbounded_ranges():
    with pytest.raises(ValueError, match="1..31"):
        await GalaxyCollector().collect_range(date(2026, 8, 20), days=0)
