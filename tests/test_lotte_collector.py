import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app.collectors.lotte import LotteCollector

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_lotte_cinema_and_schedule():
    html = (
        '<a href="/Cinema-Detail.aspx?divisionCode=1&amp;detailDivisionCode=1'
        '&amp;cinemaID=8009" title="Cantavil">Cantavil</a>'
    )
    discovered = LotteCollector.discover_cinemas(html)
    assert discovered[0]["cinema_id"] == "8009"
    assert discovered[0]["detail_division_code"] == "1"

    cinema = LotteCollector.parse_cinema_detail(
        _fixture("lotte_cinema_detail.json")
    )
    assert cinema.name == "Lotte Cinema Cantavil"
    assert cinema.city == "Hồ Chí Minh"
    assert str(cinema.latitude) == "10.801439"

    movies = LotteCollector.parse_movies(_fixture("lotte_movies.json"))
    items = LotteCollector.parse_play_sequence(
        _fixture("lotte_play_sequence.json"), {"8009": cinema}, movies
    )
    assert len(items) == 1
    item = items[0]
    assert item.external_id == "8009-20260820-800901-3"
    assert item.movie.external_id == "12203"
    assert item.movie.duration_minutes == 117
    assert item.movie.poster_url == "https://example.com/lotte-poster.jpg"
    assert item.movie.genres == "Hài, Gia đình"
    assert item.start_time.isoformat() == "2026-08-20T23:30:00+07:00"
    assert item.booking_mode == "external_redirect"


def test_parse_lotte_available_dates():
    dates = LotteCollector.parse_available_dates(_fixture("lotte_play_dates.json"))
    assert dates == {date(2026, 8, 20), date(2026, 8, 21)}


def test_parse_lotte_movie_detail_fallback():
    movie = LotteCollector.parse_movie_detail(_fixture("lotte_movie_detail.json"))
    assert movie.external_id == "12203"
    assert movie.duration_minutes == 117
    assert movie.genres == "Comedy"
    assert movie.poster_url == "https://example.com/lotte-detail-poster.jpg"


@pytest.mark.asyncio
async def test_lotte_collect_range_uses_rpc_pipeline():
    cinema_html = (
        '<a href="/Cinema-Detail.aspx?divisionCode=1&amp;detailDivisionCode=1'
        '&amp;cinemaID=8009" title="Cantavil">Cantavil</a>'
    )
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=cinema_html)
        payload = json.loads(parse_qs(request.content.decode())["paramList"][0])
        method = payload["MethodName"]
        methods.append(method)
        fixtures = {
            "GetCinemaDetailItem": "lotte_cinema_detail.json",
            "GetMoviePlayDates": "lotte_play_dates.json",
            "GetMovies": "lotte_movies.json",
            "GetPlaySequence": "lotte_play_sequence.json",
        }
        return httpx.Response(200, json=_fixture(fixtures[method]))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://lotte.test"
    ) as client:
        collector = LotteCollector(
            base_url="https://lotte.test",
            client=client,
            request_interval_seconds=0,
        )
        items = await collector.collect_range(date(2026, 8, 20), days=1)

    assert [item.external_id for item in items] == ["8009-20260820-800901-3"]
    assert methods == [
        "GetCinemaDetailItem",
        "GetMoviePlayDates",
        "GetMovies",
        "GetPlaySequence",
    ]


@pytest.mark.asyncio
async def test_lotte_collect_range_validates_days():
    with pytest.raises(ValueError, match="1..31"):
        await LotteCollector().collect_range(date(2026, 8, 20), days=0)
