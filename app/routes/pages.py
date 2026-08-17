"""
Route render HTML bằng Jinja2 — khác với các route JSON API (movies.py,
booking.py...), các route ở đây trả về HTML để hiển thị trực tiếp trên
trình duyệt. Logic nghiệp vụ (đặt vé, đăng nhập...) vẫn dùng LẠI các API
JSON đã xây, gọi qua JavaScript fetch() từ phía client.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.templates import templates
from app.models.movie import Movie
from app.models.showtime import Showtime
from app.services.tmdb import get_trailer_key

router = APIRouter(tags=["pages"])


@router.get("/")
async def home_page(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Movie).limit(24))
    movies = result.scalars().all()
    return templates.TemplateResponse(
        request=request, name="index.html", context={"movies": movies}
    )


@router.get("/movie/{movie_id}")
async def movie_detail_page(
    movie_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    movie = await db.get(Movie, movie_id)
    if movie is None:
        return templates.TemplateResponse(
            request=request, name="404.html", status_code=404
        )

    result = await db.execute(
        select(Showtime).where(Showtime.movie_id == movie_id)
    )
    showtimes = result.scalars().all()

    # Chỉ phim được import từ TMDB (có tmdb_id) mới tra được trailer.
    # Phim nhập tay qua POST /movies sẽ không có trailer -> trailer_key=None,
    # template tự ẩn phần trailer nếu không có (xem movie_detail.html).
    trailer_key = None
    if movie.tmdb_id is not None:
        trailer_key = await get_trailer_key(movie.tmdb_id)

    return templates.TemplateResponse(
        request=request,
        name="movie_detail.html",
        context={"movie": movie, "showtimes": showtimes, "trailer_key": trailer_key},
    )


@router.get("/showtime/{showtime_id}/seats")
async def seat_selection_page(
    showtime_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    query = (
        select(Showtime)
        .where(Showtime.id == showtime_id)
        .options(selectinload(Showtime.seats), selectinload(Showtime.movie))
    )
    result = await db.execute(query)
    showtime = result.scalar_one_or_none()

    if showtime is None:
        return templates.TemplateResponse(
            request=request, name="404.html", status_code=404
        )

    seats_by_row: dict[str, list] = {}
    for seat in showtime.seats:
        seats_by_row.setdefault(seat.row_label, []).append(seat)
    for row in seats_by_row.values():
        row.sort(key=lambda s: s.col_number)

    return templates.TemplateResponse(
        request=request,
        name="seats.html",
        context={"showtime": showtime, "seats_by_row": seats_by_row},
    )


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html")


@router.get("/my-bookings")
async def my_bookings_page(request: Request):
    return templates.TemplateResponse(request=request, name="my_bookings.html")

@router.get("/forgot-password")
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(request=request, name="forgot_password.html")


@router.get("/reset-password")
async def reset_password_page(request: Request, token: str = ""):
    return templates.TemplateResponse(
        request=request, name="reset_password.html", context={"token": token}
    )