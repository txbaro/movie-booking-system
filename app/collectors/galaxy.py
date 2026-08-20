"""Collector lịch chiếu từ dữ liệu Next.js công khai của Galaxy Cinema."""

import asyncio
import json
import os
import re
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app.collectors.base import CinemaCollector
from app.collectors.schemas import CollectedCinema, CollectedMovie, CollectedShowtime

VIETNAM_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
NEXT_DATA_PATTERN = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.DOTALL
)


class GalaxyCollectorError(RuntimeError):
    """Galaxy không phản hồi hoặc thay đổi schema dữ liệu."""


def _page_props(html: str) -> dict[str, Any]:
    match = NEXT_DATA_PATTERN.search(html)
    if match is None:
        raise GalaxyCollectorError("Không tìm thấy __NEXT_DATA__ trong HTML Galaxy")
    try:
        return json.loads(match.group(1))["props"]["pageProps"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise GalaxyCollectorError("__NEXT_DATA__ Galaxy không đúng schema") from exc


def _result(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = (payload.get("data") or {}).get("result") or []
    return rows if isinstance(rows, list) else []


def _coordinate(value: Any, minimum: int, maximum: int) -> Decimal | None:
    try:
        result = Decimal(str(value)).quantize(Decimal("0.000001"))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if minimum <= result <= maximum else None


def _positive_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


class GalaxyCollector(CinemaCollector):
    source = "galaxy"
    schedule_path = "/lich-chieu/"

    def __init__(
        self,
        *,
        base_url: str = "https://www.galaxycine.vn",
        timeout_seconds: float = 30.0,
        max_attempts: int = 3,
        request_interval_seconds: float = 0.5,
        cookie: str | None = None,
        user_agent: str | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.request_interval_seconds = request_interval_seconds
        self.cookie = cookie if cookie is not None else os.getenv("GALAXY_COOKIE")
        self.user_agent = user_agent or os.getenv("GALAXY_USER_AGENT") or (
            "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/151.0.0.0 Mobile Safari/537.36"
        )
        self._client = client
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def _throttle(self) -> None:
        async with self._request_lock:
            remaining = self.request_interval_seconds - (
                time.monotonic() - self._last_request_at
            )
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_request_at = time.monotonic()

    async def _get_schedule_page(self, client: httpx.AsyncClient) -> str:
        url = f"{self.base_url}{self.schedule_path}"
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            await self._throttle()
            try:
                response = await client.get(url)
                if response.is_redirect:
                    raise GalaxyCollectorError(
                        "Galaxy yêu cầu cookie chống bot. Hãy cập nhật GALAXY_COOKIE "
                        "từ request /lich-chieu trong DevTools."
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Galaxy HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response.text
            except GalaxyCollectorError:
                raise
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    await asyncio.sleep(2 ** (attempt - 1))
        raise GalaxyCollectorError(f"Không thể tải {url}: {last_error}")

    @staticmethod
    def parse_schedule_page(
        html: str,
        target_dates: set[date],
        base_url: str = "https://www.galaxycine.vn",
    ) -> list[CollectedShowtime]:
        props = _page_props(html)
        sessions = _result(props.get("dataSessonAll"))
        cinemas = {
            str(row.get("id")): row
            for row in _result(props.get("dataCinemas"))
            if row.get("id")
        }
        movies = {
            str(row.get("id")): row
            for key in ("dataMovie", "dataComming")
            for row in _result(props.get(key))
            if row.get("id")
        }
        cities = {
            str(row.get("id")): str(row.get("name") or "Chưa cập nhật").strip()
            for row in (props.get("cityFilter") or [])
            if isinstance(row, dict) and row.get("id")
        }

        collected: dict[str, CollectedShowtime] = {}
        for row in sessions:
            try:
                show_date = date.fromisoformat(str(row["showDate"]))
            except (KeyError, TypeError, ValueError):
                continue
            if show_date not in target_dates:
                continue

            session_id = str(row.get("id") or "").strip()
            embedded_movie = row.get("movie") or {}
            embedded_cinema = row.get("cinema") or {}
            movie_id = str(embedded_movie.get("id") or "").strip()
            cinema_id = str(embedded_cinema.get("id") or "").strip()
            if not session_id or not movie_id or not cinema_id:
                continue
            raw_movie = {**movies.get(movie_id, {}), **embedded_movie}
            raw_cinema = {**cinemas.get(cinema_id, {}), **embedded_cinema}

            duration = _positive_int(raw_movie.get("duration"))
            title = str(raw_movie.get("name") or "").strip()
            if duration is None or not title:
                continue
            try:
                start_time = datetime.strptime(
                    f"{row['showDate']} {row['showTime']}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=VIETNAM_TIMEZONE)
            except (KeyError, TypeError, ValueError):
                continue

            latitude = _coordinate(raw_cinema.get("latitude"), -90, 90)
            longitude = _coordinate(raw_cinema.get("longitude"), -180, 180)
            if (latitude is None) != (longitude is None):
                latitude = longitude = None
            cinema = CollectedCinema(
                external_id=cinema_id,
                name=str(raw_cinema.get("name") or "Galaxy Cinema").strip(),
                address=str(raw_cinema.get("address") or "Chưa cập nhật").strip(),
                city=cities.get(
                    str(raw_cinema.get("cityId") or ""), "Chưa cập nhật"
                ),
                latitude=latitude,
                longitude=longitude,
            )
            try:
                rating = min(10.0, max(0.0, float(raw_movie.get("rate") or 0)))
            except (TypeError, ValueError):
                rating = 0.0
            movie = CollectedMovie(
                external_id=movie_id,
                title=title,
                genres="Chưa phân loại",
                description="Thông tin phim từ Galaxy Cinema.",
                duration_minutes=duration,
                rating=rating,
                poster_url=raw_movie.get("imagePortrait") or None,
            )
            slug = str(raw_movie.get("slug") or movie_id).strip()
            booking_url = (
                f"{base_url.rstrip('/')}/booking/{quote(slug, safe='-')}"
                f"?sessionId={quote(session_id, safe='-')}"
            )
            caption = str(row.get("caption") or "").strip().lower()
            language = {"sub": "Phụ đề", "dub": "Lồng tiếng"}.get(
                caption, caption or None
            )
            collected[session_id] = CollectedShowtime(
                external_id=session_id,
                cinema=cinema,
                movie=movie,
                start_time=start_time,
                booking_mode="external_redirect",
                external_booking_url=booking_url,
                format=str(row.get("movieFormat") or row.get("version") or "").strip()
                or None,
                language=language,
            )
        return list(collected.values())

    async def _collect_dates(self, target_dates: set[date]) -> list[CollectedShowtime]:
        owns_client = self._client is None
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/json",
            "User-Agent": self.user_agent,
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        client = self._client or httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=False,
            headers=headers,
        )
        try:
            html = await self._get_schedule_page(client)
            return self.parse_schedule_page(html, target_dates, self.base_url)
        finally:
            if owns_client:
                await client.aclose()

    async def collect(self, target_date: date) -> list[CollectedShowtime]:
        return await self._collect_dates({target_date})

    async def collect_range(
        self, start_date: date, days: int = 7
    ) -> list[CollectedShowtime]:
        if not 1 <= days <= 31:
            raise ValueError("days phải nằm trong khoảng 1..31")
        target_dates = {start_date + timedelta(days=offset) for offset in range(days)}
        return await self._collect_dates(target_dates)
