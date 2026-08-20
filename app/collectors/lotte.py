"""Collector lịch chiếu công khai từ các RPC endpoint ASP.NET của Lotte."""

import asyncio
import html as html_module
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
from app.collectors.schemas import CollectedCinema, CollectedMovie, CollectedShowtime

logger = logging.getLogger(__name__)

VIETNAM_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
CINEMA_LINK_PATTERN = re.compile(
    r"divisionCode=(\d+)&(?:amp;)?detailDivisionCode=(\d+)"
    r"&(?:amp;)?cinemaID=(\d+)[^>]+title=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)


class LotteCollectorError(RuntimeError):
    """Lotte không phản hồi hoặc thay đổi schema RPC."""


def _decimal_coordinate(value: Any, minimum: int, maximum: int) -> Decimal | None:
    try:
        result = Decimal(str(value)).quantize(Decimal("0.000001"))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if minimum <= result <= maximum else None


def _city_name(value: Any) -> str:
    raw = str(value or "").strip()
    aliases = {
        "Ho Chi Minh City": "Hồ Chí Minh",
        "Hanoi": "Hà Nội",
        "Ha Noi": "Hà Nội",
    }
    return aliases.get(raw, raw or "Chưa cập nhật")


class LotteCollector(CinemaCollector):
    source = "lotte"

    cinema_page_path = "/LCHS/Contents/Cinema/Cinema-Detail.aspx"
    cinema_rpc_path = "/LCWS/Cinema/CinemaData.aspx"
    ticketing_rpc_path = "/LCWS/Ticketing/TicketingData.aspx"
    movie_rpc_path = "/LCWS/Movie/MovieData.aspx"

    def __init__(
        self,
        *,
        base_url: str = "https://www.lottecinemavn.com",
        timeout_seconds: float = 25.0,
        max_attempts: int = 3,
        request_interval_seconds: float = 0.35,
        max_concurrency: int = 6,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.request_interval_seconds = request_interval_seconds
        self._client = client
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def _throttle(self) -> None:
        async with self._request_lock:
            remaining = self.request_interval_seconds - (
                time.monotonic() - self._last_request_at
            )
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_request_at = time.monotonic()

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        last_error: Exception | None = None
        async with self._semaphore:
            for attempt in range(1, self.max_attempts + 1):
                await self._throttle()
                try:
                    response = await client.request(method, url, **kwargs)
                    if response.status_code == 429 or response.status_code >= 500:
                        raise httpx.HTTPStatusError(
                            f"Lotte HTTP {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    response.raise_for_status()
                    return response
                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    last_error = exc
                    if attempt < self.max_attempts:
                        await asyncio.sleep(2 ** (attempt - 1))
        raise LotteCollectorError(f"Không thể tải {url}: {last_error}")

    async def _rpc(
        self,
        client: httpx.AsyncClient,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self._request(
            client,
            "POST",
            f"{self.base_url}{path}",
            data={"paramList": json.dumps(payload, ensure_ascii=False)},
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise LotteCollectorError(f"RPC {payload['MethodName']} không trả JSON") from exc
        if str(data.get("IsOK", "")).lower() != "true":
            raise LotteCollectorError(
                f"RPC {payload['MethodName']} lỗi: {data.get('ResultMessage')}"
            )
        return data

    @staticmethod
    def discover_cinemas(html: str) -> list[dict[str, str]]:
        cinemas: dict[str, dict[str, str]] = {}
        for division, detail_division, cinema_id, name in CINEMA_LINK_PATTERN.findall(
            html
        ):
            cinemas[cinema_id] = {
                "division_code": division,
                "detail_division_code": detail_division,
                "cinema_id": cinema_id,
                "name": html_module.unescape(name).strip(),
            }
        if not cinemas:
            raise LotteCollectorError("Không tìm thấy danh sách rạp trong HTML")
        return list(cinemas.values())

    @staticmethod
    def parse_cinema_detail(payload: dict[str, Any]) -> CollectedCinema:
        item = payload.get("CinemaDetail") or {}
        cinema_id = str(item.get("CinemaID") or "").strip()
        if not cinema_id:
            raise LotteCollectorError("CinemaDetail thiếu CinemaID")
        latitude = _decimal_coordinate(item.get("Latitude"), -90, 90)
        longitude = _decimal_coordinate(item.get("Longitude"), -180, 180)
        if (latitude is None) != (longitude is None):
            latitude = longitude = None
        name = str(item.get("CinemaName") or item.get("CinemaNameUS") or "").strip()
        return CollectedCinema(
            external_id=cinema_id,
            name=f"Lotte Cinema {name}",
            address=str(item.get("Address") or "Chưa cập nhật").strip(),
            city=_city_name(item.get("Province")),
            latitude=latitude,
            longitude=longitude,
        )

    @staticmethod
    def parse_available_dates(payload: dict[str, Any]) -> set[date]:
        rows = (payload.get("Items") or {}).get("Items") or []
        result = set()
        for row in rows:
            if row.get("IsPlayDate") != "Y":
                continue
            try:
                result.add(datetime.strptime(row["PlayDate"], "%Y%m%d").date())
            except (KeyError, TypeError, ValueError):
                continue
        return result

    @staticmethod
    def parse_movies(payload: dict[str, Any]) -> dict[str, CollectedMovie]:
        rows = (payload.get("Movies") or {}).get("Items") or []
        result = {}
        for row in rows:
            movie_code = str(row.get("RepresentationMovieCode") or "").strip()
            title = str(row.get("MovieName") or row.get("MovieNameUS") or "").strip()
            try:
                duration = int(row.get("PlayTime"))
            except (TypeError, ValueError):
                continue
            if not movie_code or not title or duration <= 0:
                continue
            raw_rating = row.get("ViewEvaluation") or row.get("Evaluation") or 0
            try:
                rating = min(10.0, max(0.0, float(raw_rating)))
            except (TypeError, ValueError):
                rating = 0.0
            result[movie_code] = CollectedMovie(
                external_id=movie_code,
                title=title,
                genres=str(row.get("MovieGenreName") or "Chưa phân loại").strip(),
                description=str(
                    row.get("TopReview") or "Thông tin phim từ Lotte Cinema."
                ).strip(),
                duration_minutes=duration,
                rating=rating,
                poster_url=(row.get("PosterURL") or None),
            )
        return result

    @staticmethod
    def parse_movie_detail(payload: dict[str, Any]) -> CollectedMovie:
        row = payload.get("Movie") or {}
        movie_code = str(row.get("RepresentationMovieCode") or "").strip()
        title = str(row.get("MovieName") or row.get("MovieNameUS") or "").strip()
        try:
            duration = int(row.get("PlayTime"))
        except (TypeError, ValueError) as exc:
            raise LotteCollectorError("Movie detail thiếu PlayTime") from exc
        if not movie_code or not title or duration <= 0:
            raise LotteCollectorError("Movie detail thiếu mã, tên hoặc thời lượng")
        raw_rating = row.get("ViewEvaluation") or row.get("Evaluation") or 0
        try:
            rating = min(10.0, max(0.0, float(raw_rating)))
        except (TypeError, ValueError):
            rating = 0.0
        return CollectedMovie(
            external_id=movie_code,
            title=title,
            genres=str(row.get("MovieGenreName") or "Chưa phân loại").strip(),
            description=str(
                row.get("Synopsis")
                or row.get("TopReview")
                or "Thông tin phim từ Lotte Cinema."
            ).strip(),
            duration_minutes=duration,
            rating=rating,
            poster_url=(row.get("PosterURL") or None),
        )

    @staticmethod
    def parse_play_sequence(
        payload: dict[str, Any],
        cinemas: dict[str, CollectedCinema],
        movies: dict[str, CollectedMovie] | None = None,
        base_url: str = "https://www.lottecinemavn.com",
    ) -> list[CollectedShowtime]:
        headers = (payload.get("PlaySeqsHeader") or {}).get("Items") or []
        rows = (payload.get("PlaySeqs") or {}).get("Items") or []
        movie_headers: dict[tuple[str, str], dict] = {}
        for header in headers:
            key = (
                str(header.get("CinemaID") or ""),
                str(header.get("RepresentationMovieCode") or header.get("MovieCode") or ""),
            )
            if all(key) and key not in movie_headers:
                movie_headers[key] = header

        result = []
        for row in rows:
            cinema_id = str(row.get("CinemaID") or "")
            movie_code = str(
                row.get("RepresentationMovieCode") or row.get("MovieCode") or ""
            )
            cinema = cinemas.get(cinema_id)
            header = movie_headers.get((cinema_id, movie_code))
            if cinema is None or header is None or row.get("IsBookingYN") != "Y":
                continue
            try:
                start = datetime.strptime(
                    f"{row['PlayDt']} {row['StartTime']}", "%Y%m%d %H:%M"
                ).replace(tzinfo=VIETNAM_TIMEZONE)
                end = datetime.strptime(
                    f"{row['PlayDt']} {row['EndTime']}", "%Y%m%d %H:%M"
                ).replace(tzinfo=VIETNAM_TIMEZONE)
            except (KeyError, TypeError, ValueError):
                continue
            if end <= start:
                end += timedelta(days=1)
            duration = max(1, int((end - start).total_seconds() // 60))
            title = str(header.get("MovieName") or header.get("MovieNameUS") or "").strip()
            if not title:
                continue
            screen_id = str(row.get("ScreenID") or "")
            play_sequence = str(row.get("PlaySequence") or "")
            if not screen_id or not play_sequence:
                continue
            movie = (movies or {}).get(movie_code)
            if movie is None:
                movie = CollectedMovie(
                    external_id=movie_code,
                    title=title,
                    genres="Chưa phân loại",
                    description="Thông tin phim từ Lotte Cinema.",
                    duration_minutes=duration,
                    poster_url=(header.get("ImageUrl") or None),
                )
            result.append(
                CollectedShowtime(
                    external_id=(
                        f"{cinema_id}-{row['PlayDt']}-{screen_id}-{play_sequence}"
                    ),
                    cinema=cinema,
                    movie=movie,
                    start_time=start,
                    booking_mode="external_redirect",
                    external_booking_url=(
                        f"{base_url.rstrip('/')}/LCHS/Contents/ticketing/"
                        "movie-schedule.aspx"
                    ),
                    format=(header.get("FilmName") or header.get("FilmNameUS") or None),
                    language=(
                        header.get("TranslationDivisionName")
                        or header.get("TranslationDivisionNameUS")
                        or None
                    ),
                )
            )
        return result

    @staticmethod
    def _common_payload(method_name: str) -> dict[str, Any]:
        return {
            "MethodName": method_name,
            "channelType": "HO",
            "osType": "Chrome",
            "osVersion": "Mozilla/5.0",
            "multiLanguageID": "LL",
        }

    async def _collect_dates(self, target_dates: set[date]) -> list[CollectedShowtime]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": "Mozilla/5.0 (compatible; MovieBookingCollector/1.0)",
            },
        )
        try:
            page = await self._request(
                client, "GET", f"{self.base_url}{self.cinema_page_path}"
            )
            discovered = self.discover_cinemas(page.text)

            async def load_cinema(item: dict[str, str]):
                payload = self._common_payload("GetCinemaDetailItem") | {
                    "divisionCode": item["division_code"],
                    "detailDivisionCode": item["detail_division_code"],
                    "cinemaID": item["cinema_id"],
                    "memberOnNo": 0,
                }
                try:
                    detail = await self._rpc(client, self.cinema_rpc_path, payload)
                    return item, self.parse_cinema_detail(detail)
                except Exception as exc:
                    logger.warning("Bỏ qua rạp Lotte %s: %s", item["cinema_id"], exc)
                    return item, None

            loaded = await asyncio.gather(*(load_cinema(item) for item in discovered))
            cinema_meta = {
                item["cinema_id"]: item for item, cinema in loaded if cinema is not None
            }
            cinemas = {
                item["cinema_id"]: cinema
                for item, cinema in loaded
                if cinema is not None
            }

            dates_payload = await self._rpc(
                client,
                self.ticketing_rpc_path,
                self._common_payload("GetMoviePlayDates"),
            )
            dates = self.parse_available_dates(dates_payload) & target_dates
            movies_payload = await self._rpc(
                client,
                self.movie_rpc_path,
                self._common_payload("GetMovies")
                | {
                    "division": 1,
                    "moviePlayYN": "Y",
                    "orderType": "1",
                    "blockSize": 100,
                    "pageNo": 1,
                    "memberNoOn": "",
                },
            )
            movies = self.parse_movies(movies_payload)

            async def load_schedule(cinema_id: str, play_date: date):
                meta = cinema_meta[cinema_id]
                payload = self._common_payload("GetPlaySequence") | {
                    "playDate": play_date.strftime("%Y%m%d"),
                    "cinemaID": (
                        f"{meta['division_code']}|"
                        f"{int(meta['detail_division_code'])}|{cinema_id}"
                    ),
                    "representationMovieCode": "",
                }
                try:
                    response = await self._rpc(
                        client, self.ticketing_rpc_path, payload
                    )
                    return self.parse_play_sequence(
                        response, cinemas, movies, self.base_url
                    )
                except Exception as exc:
                    logger.warning(
                        "Bỏ qua lịch Lotte rạp %s ngày %s: %s",
                        cinema_id,
                        play_date,
                        exc,
                    )
                    return []

            batches = await asyncio.gather(
                *(
                    load_schedule(cinema_id, play_date)
                    for cinema_id in cinemas
                    for play_date in dates
                )
            )
            items = [item for batch in batches for item in batch]
            missing_movie_codes = {
                item.movie.external_id for item in items if item.movie.external_id not in movies
            }

            async def load_missing_movie(movie_code: str):
                payload = self._common_payload("GetMovieDetail") | {
                    "representationMovieCode": movie_code
                }
                try:
                    response = await self._rpc(client, self.movie_rpc_path, payload)
                    return movie_code, self.parse_movie_detail(response)
                except Exception as exc:
                    logger.warning("Không thể enrich phim Lotte %s: %s", movie_code, exc)
                    return movie_code, None

            enriched = dict(
                await asyncio.gather(
                    *(load_missing_movie(code) for code in missing_movie_codes)
                )
            )
            for item in items:
                movie = enriched.get(item.movie.external_id)
                if movie is not None:
                    item.movie = movie
            return list({item.external_id: item for item in items}.values())
        finally:
            if owns_client:
                await client.aclose()

    async def collect(self, target_date: date) -> list[CollectedShowtime]:
        return await self._collect_dates({target_date})

    async def collect_range(self, start_date: date, days: int = 7):
        if not 1 <= days <= 31:
            raise ValueError("days phải nằm trong khoảng 1..31")
        dates = {start_date + timedelta(days=offset) for offset in range(days)}
        return await self._collect_dates(dates)
