from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.collectors.schemas import CollectedCinema, CollectedMovie, CollectedShowtime
from app.core.database import AsyncSessionLocal
from app.models.movie import Movie
from app.models.provider_movie import ProviderMovie
from app.models.showtime import Showtime
from app.services.cinema_sync import sync_collected_showtimes
from app.services.discovery import VIETNAM_TIMEZONE, utc_now


def _showtime(
    *,
    source: str,
    showtime_id: str,
    movie_id: str,
    title: str,
    start_offset_hours: int,
) -> CollectedShowtime:
    return CollectedShowtime(
        external_id=showtime_id,
        cinema=CollectedCinema(
            external_id=f"{source}-cinema",
            name=f"{source.title()} Cinema",
            address="1 Test Street",
            city="Hồ Chí Minh",
            latitude=Decimal("10.776900"),
            longitude=Decimal("106.700900"),
        ),
        movie=CollectedMovie(
            external_id=movie_id,
            title=title,
            genres="Gia đình" if source == "cinestar" else "Chưa phân loại",
            description=f"Thông tin phim từ {source}.",
            duration_minutes=117,
            rating=8.5,
            poster_url=f"https://cdn.example/{source}.jpg",
        ),
        start_time=(utc_now() + timedelta(hours=start_offset_hours)).astimezone(
            VIETNAM_TIMEZONE
        ),
        booking_mode="external_redirect",
        external_booking_url=f"https://{source}.example/booking/{showtime_id}",
        format="2D",
        language="Phụ đề",
    )


@pytest.mark.asyncio
async def test_sync_merges_provider_movies_into_one_canonical_movie(client):
    cinestar = _showtime(
        source="cinestar",
        showtime_id="cinestar-showtime",
        movie_id="cinestar-movie",
        title="NGHỈ HÈ SỢ NGHỈ HƯU (T13)",
        start_offset_hours=25,
    )
    galaxy = _showtime(
        source="galaxy",
        showtime_id="galaxy-showtime",
        movie_id="galaxy-movie",
        title="Nghỉ Hè Sợ Nghỉ Hưu",
        start_offset_hours=26,
    )

    async with AsyncSessionLocal() as db:
        first = await sync_collected_showtimes(db, "cinestar", [cinestar])
        second = await sync_collected_showtimes(db, "galaxy", [galaxy])
        repeated = await sync_collected_showtimes(db, "galaxy", [galaxy])

        assert first.created == 1
        assert second.created == 1
        assert repeated.skipped == 1
        assert await db.scalar(select(func.count(Movie.id))) == 1
        assert await db.scalar(select(func.count(ProviderMovie.id))) == 2
        assert await db.scalar(select(func.count(Showtime.id))) == 2
        movie = await db.scalar(select(Movie))
        movie_ids = set((await db.scalars(select(Showtime.movie_id))).all())

    assert movie is not None
    assert movie.title == "Nghỉ Hè Sợ Nghỉ Hưu"
    assert movie.genres == "Gia đình"
    assert movie.metadata_source == "galaxy"
    assert movie_ids == {movie.id}

    cinestar_movies = await client.get("/movies", params={"source": "cinestar"})
    galaxy_movies = await client.get("/movies", params={"source": "galaxy"})
    assert cinestar_movies.json()[0]["id"] == galaxy_movies.json()[0]["id"]
