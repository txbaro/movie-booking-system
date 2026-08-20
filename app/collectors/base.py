from abc import ABC, abstractmethod
from datetime import date

from app.collectors.schemas import CollectedShowtime


class CinemaCollector(ABC):
    source: str

    @abstractmethod
    async def collect(self, target_date: date) -> list[CollectedShowtime]:
        raise NotImplementedError
