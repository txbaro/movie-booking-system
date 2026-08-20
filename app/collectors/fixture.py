import asyncio
import json
from datetime import date
from pathlib import Path

from app.collectors.base import CinemaCollector
from app.collectors.schemas import CollectedShowtime


class FixtureCollector(CinemaCollector):
    source = "fixture"

    def __init__(self, fixture_path: Path, source: str = "fixture"):
        self.fixture_path = fixture_path
        self.source = source

    async def collect(self, target_date: date) -> list[CollectedShowtime]:
        content = await asyncio.to_thread(self.fixture_path.read_text, encoding="utf-8")
        raw_items = json.loads(content)
        items = [CollectedShowtime.model_validate(item) for item in raw_items]
        return [item for item in items if item.start_time.date() == target_date]
