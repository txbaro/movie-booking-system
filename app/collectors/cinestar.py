"""Collector dữ liệu lịch chiếu công khai từ website Cinestar."""

import asyncio
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.collectors.base import CinemaCollector
from app.collectors.schemas import (
    CollectedCinema,
    CollectedMovie,
    CollectedShowtime,
)

logger = logging.getLogger(__name__)

VIETNAM_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
NEXT_DATA_PATTERN = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL,
)


class CinestarCollectorError(RuntimeError):
    """Cinestar không phản hồi hoặc thay đổi cấu trúc dữ liệu."""


def _next_page_props(html: str) -> dict[str, Any]:
    match = NEXT_DATA_PATTERN.search(html)
    if match is None:
        raise CinestarCollectorError("Không tìm thấy __NEXT_DATA__ trong HTML")
    try:
        payload = json.loads(match.group(1))
        return payload["props"]["pageProps"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CinestarCollectorError("__NEXT_DATA__ không đúng schema mong đợi") from exc


def _coordinates(raw_maps: Any) -> tuple[Decimal | None, Decimal | None]:
    if not isinstance(raw_maps, str) or "," not in raw_maps:
        return None, None
    raw_latitude, raw_longitude = raw_maps.split(",", 1)
    try:
        precision = Decimal("0.000001")
        latitude = Decimal(raw_latitude.strip()).quantize(precision)
        longitude = Decimal(raw_longitude.strip()).quantize(precision)
    except InvalidOperation:
        return None, None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None, None
    return latitude, longitude


def _positive_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


class CinestarCollector(CinemaCollector):
    source = "cinestar"

    def __init__(
        self,
        *,
        base_url: str = "https://cinestar.com.vn",
        timeout_seconds: float = 20.0,
        max_attempts: int = 3,
        request_interval_seconds: float = 0.5,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.request_interval_seconds = request_interval_seconds
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

    async def _get_text(self, client: httpx.AsyncClient, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            await self._throttle()
            try:
                response = await client.get(url)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Cinestar HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response.text
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    await asyncio.sleep(2 ** (attempt - 1))
        raise CinestarCollectorError(f"Không thể tải {url}: {last_error}")

    @staticmethod
    def parse_homepage(html: str) -> tuple[list[dict], dict[str, dict]]:
        response = _next_page_props(html).get("res") or {}
        movies = response.get("listMovie") or []
        cinemas = response.get("listCinemas") or []
        if not isinstance(movies, list) or not isinstance(cinemas, list):
            raise CinestarCollectorError("Homepage thiếu listMovie/listCinemas")
        cinema_by_id = {
            item["id"]: item
            for item in cinemas
            if isinstance(item, dict) and item.get("id")
        }
        return movies, cinema_by_id

    @staticmethod
    def parse_movie_page(
        html: str,
        target_date: date | set[date],
        cinema_by_id: dict[str, dict],
        base_url: str = "https://cinestar.com.vn",
    ) -> list[CollectedShowtime]:
        response = _next_page_props(html).get("res") or {}
        movie_raw = response.get("movieData") or {}
        schedule = (response.get("dataShowTime") or {}).get("schedule") or []
        movie_id = str(movie_raw.get("id") or "").strip()
        duration = _positive_int(movie_raw.get("time") or movie_raw.get("time_m"))
        if not movie_id or duration is None:
            raise CinestarCollectorError("Trang phim thiếu id hoặc thời lượng")

        movie = CollectedMovie(
            external_id=movie_id,
            title=(movie_raw.get("name_vn") or movie_raw.get("name_en") or "").strip(),
            genres=(movie_raw.get("type_name_vn") or "Chưa phân loại").strip(),
            description=(
                movie_raw.get("brief_vn")
                or movie_raw.get("desc_vn")
                or "Chưa có mô tả"
            ).strip(),
            duration_minutes=duration,
            poster_url=(movie_raw.get("image") or None),
        )
        target_dates = {target_date} if isinstance(target_date, date) else target_date
        showtimes: list[CollectedShowtime] = []
        for day in schedule:
            try:
                schedule_date = datetime.strptime(day["date"], "%d/%m/%Y").date()
            except (KeyError, TypeError, ValueError):
                continue
            if schedule_date not in target_dates:
                continue
            for raw_time in day.get("times") or []:
                cinema_id = str(raw_time.get("theater_id") or "").strip()
                cinema_raw = cinema_by_id.get(cinema_id)
                showtime_id = str(raw_time.get("showtime_id") or "").strip()
                if cinema_raw is None or not showtime_id:
                    continue
                try:
                    start_time = datetime.strptime(
                        f"{day['date']} {raw_time['time']}", "%d/%m/%Y %H:%M"
                    ).replace(tzinfo=VIETNAM_TIMEZONE)
                except (KeyError, TypeError, ValueError):
                    continue
                latitude, longitude = _coordinates(cinema_raw.get("maps"))
                cinema = CollectedCinema(
                    external_id=cinema_id,
                    name=(
                        cinema_raw.get("name_vn")
                        or raw_time.get("theater_name_vn")
                        or "Cinestar"
                    ).strip(),
                    address=(cinema_raw.get("address") or "Chưa cập nhật").strip(),
                    city=(
                        cinema_raw.get("area_name_vn") or "Chưa cập nhật"
                    ).strip(),
                    latitude=latitude,
                    longitude=longitude,
                )
                showtimes.append(
                    CollectedShowtime(
                        external_id=showtime_id,
                        cinema=cinema,
                        movie=movie,
                        start_time=start_time,
                        booking_mode="external_redirect",
                        external_booking_url=f"{base_url.rstrip('/')}/movie/{movie_id}/",
                        format=(
                            movie_raw.get("formats_name_vn")
                            or raw_time.get("room_type_name_vn")
                            or None
                        ),
                        language=(movie_raw.get("language_vn") or None),
                    )
                )
        return showtimes

    async def _collect_dates(
        self, target_dates: set[date]
    ) -> list[CollectedShowtime]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/json",
                "User-Agent": "MovieBookingCollector/1.0 (+educational-project)",
            },
        )
        try:
            homepage = await self._get_text(client, f"{self.base_url}/")
            movies, cinema_by_id = self.parse_homepage(homepage)
            collected: list[CollectedShowtime] = []
            seen_movie_ids: set[str] = set()
            for movie_summary in movies:
                movie_id = str(movie_summary.get("id") or "").strip()
                if not movie_id or movie_id in seen_movie_ids:
                    continue
                seen_movie_ids.add(movie_id)
                url = f"{self.base_url}/movie/{movie_id}/"
                try:
                    movie_html = await self._get_text(client, url)
                    collected.extend(
                        self.parse_movie_page(
                            movie_html, target_dates, cinema_by_id, self.base_url
                        )
                    )
                except Exception as exc:
                    logger.warning("Bỏ qua phim Cinestar %s: %s", movie_id, exc)
            return list({item.external_id: item for item in collected}.values())
        finally:
            if owns_client:
                await client.aclose()

    async def collect(self, target_date: date) -> list[CollectedShowtime]:
        return await self._collect_dates({target_date})

    async def collect_range(
        self, start_date: date, days: int = 7
    ) -> list[CollectedShowtime]:
        """Thu lịch trong ``days`` ngày bằng cùng một lượt tải dữ liệu nguồn."""
        if not 1 <= days <= 31:
            raise ValueError("days phải nằm trong khoảng 1..31")
        target_dates = {start_date + timedelta(days=offset) for offset in range(days)}
        return await self._collect_dates(target_dates)
