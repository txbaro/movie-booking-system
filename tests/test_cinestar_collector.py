from datetime import date
from pathlib import Path

import httpx
import pytest

from app.collectors.cinestar import CinestarCollector, CinestarCollectorError

FIXTURES = Path(__file__).parent / "fixtures"


def _next_html(filename: str) -> str:
    payload = (FIXTURES / filename).read_text(encoding="utf-8")
    return f'<html><script id="__NEXT_DATA__" type="application/json">{payload}</script></html>'


def test_parse_cinestar_next_data_into_normalized_showtime():
    movies, cinemas = CinestarCollector.parse_homepage(
        _next_html("cinestar_homepage.json")
    )
    assert [movie["id"] for movie in movies] == ["movie-1"]

    items = CinestarCollector.parse_movie_page(
        _next_html("cinestar_movie.json"), date(2026, 8, 20), cinemas
    )
    assert len(items) == 1
    item = items[0]
    assert item.external_id == "showtime-1"
    assert item.movie.external_id == "movie-1"
    assert item.cinema.external_id == "cinema-1"
    assert str(item.cinema.latitude) == "10.776900"
    assert item.start_time.isoformat() == "2026-08-20T19:30:00+07:00"
    assert item.booking_mode == "external_redirect"
    assert item.price is None
    assert item.room is None


@pytest.mark.asyncio
async def test_collect_discovers_movies_without_hard_coded_ids():
    homepage = _next_html("cinestar_homepage.json")
    movie_page = _next_html("cinestar_movie.json")
    requested_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/":
            return httpx.Response(200, text=homepage)
        if request.url.path == "/movie/movie-1/":
            return httpx.Response(200, text=movie_page)
        return httpx.Response(404)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://cinestar.test"
    ) as client:
        collector = CinestarCollector(
            base_url="https://cinestar.test",
            client=client,
            request_interval_seconds=0,
        )
        items = await collector.collect(date(2026, 8, 20))

    assert [item.external_id for item in items] == ["showtime-1"]
    assert requested_paths == ["/", "/movie/movie-1/"]
    assert items[0].external_booking_url == "https://cinestar.test/movie/movie-1/"


@pytest.mark.asyncio
async def test_collect_range_fetches_once_and_includes_following_days():
    homepage = _next_html("cinestar_homepage.json")
    movie_page = _next_html("cinestar_movie.json")
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200, text=homepage if request.url.path == "/" else movie_page
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://cinestar.test"
    ) as client:
        collector = CinestarCollector(
            base_url="https://cinestar.test",
            client=client,
            request_interval_seconds=0,
        )
        items = await collector.collect_range(date(2026, 8, 20), days=7)

    assert {item.external_id for item in items} == {
        "showtime-1",
        "showtime-other-day",
    }
    assert request_count == 2


@pytest.mark.asyncio
async def test_collect_range_rejects_unbounded_ranges():
    collector = CinestarCollector()
    with pytest.raises(ValueError, match="1..31"):
        await collector.collect_range(date(2026, 8, 20), days=32)


def test_invalid_next_data_fails_with_clear_error():
    with pytest.raises(CinestarCollectorError, match="__NEXT_DATA__"):
        CinestarCollector.parse_homepage("<html></html>")
