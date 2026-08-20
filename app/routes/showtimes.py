from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.redis_client import redis_client
from app.models.booking import Booking
from app.models.cinema import Cinema
from app.models.cinema_room import CinemaRoom
from app.models.movie import Movie
from app.models.seat import Seat
from app.models.showtime import Showtime
from app.models.showtime_seat import ShowtimeSeat
from app.schemas.showtime import SeatRead, ShowtimeCreate, ShowtimeRead, ShowtimeWithSeats
from app.services.discovery import utc_now, vietnamese_date_range

router = APIRouter(prefix="/showtimes", tags=["showtimes"])


def _showtime_read(
    showtime: Showtime, room: CinemaRoom | None, cinema: Cinema
) -> ShowtimeRead:
    return ShowtimeRead(
        id=showtime.id,
        movie_id=showtime.movie_id,
        room_id=room.id if room else None,
        room_name=room.name if room else None,
        cinema_id=cinema.id,
        cinema_name=cinema.name,
        city=cinema.city,
        start_time=showtime.start_time,
        price=showtime.price,
        booking_mode=showtime.booking_mode,
        external_booking_url=showtime.external_booking_url,
        format=showtime.format,
        language=showtime.language,
        source=showtime.source,
        external_id=showtime.external_id,
        last_synced_at=showtime.last_synced_at,
    )


@router.post("", response_model=ShowtimeRead, status_code=status.HTTP_201_CREATED)
async def create_showtime(payload: ShowtimeCreate, db: AsyncSession = Depends(get_db)):
    if await db.get(Movie, payload.movie_id) is None:
        raise HTTPException(status_code=404, detail="movie_id không tồn tại")

    result = await db.execute(
        select(CinemaRoom)
        .where(CinemaRoom.id == payload.room_id)
        .options(selectinload(CinemaRoom.cinema), selectinload(CinemaRoom.seats))
    )
    room = result.scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=404, detail="room_id không tồn tại")
    if not room.seats:
        raise HTTPException(status_code=409, detail="Phòng chưa có ghế")

    rows = len({seat.row_label for seat in room.seats})
    cols = max(seat.col_number for seat in room.seats)
    showtime = Showtime(
        movie_id=payload.movie_id,
        cinema_id=room.cinema_id,
        room_id=payload.room_id,
        start_time=payload.start_time,
        price=payload.price,
        # Hai cột legacy vẫn NOT NULL trong database và sẽ được xóa ở cleanup.
        room_rows=rows,
        room_cols=cols,
    )
    db.add(showtime)
    await db.flush()
    db.add_all(
        [
            ShowtimeSeat(showtime_id=showtime.id, seat_id=seat.id)
            for seat in room.seats
        ]
    )
    await db.commit()
    await db.refresh(showtime)
    return _showtime_read(showtime, room, room.cinema)


@router.get("", response_model=list[ShowtimeRead])
async def list_showtimes(
    movie_id: int | None = None,
    cinema_id: int | None = None,
    city: str | None = None,
    source: str | None = None,
    booking_mode: str | None = Query(
        default=None, pattern="^(internal|external_redirect)$"
    ),
    show_date: date | None = Query(default=None, alias="date"),
    upcoming_only: bool = True,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Showtime, CinemaRoom, Cinema)
        .outerjoin(CinemaRoom, Showtime.room_id == CinemaRoom.id)
        .join(Cinema, Showtime.cinema_id == Cinema.id)
        .order_by(Showtime.start_time)
    )
    if movie_id is not None:
        query = query.where(Showtime.movie_id == movie_id)
    if cinema_id is not None:
        query = query.where(Showtime.cinema_id == cinema_id)
    if city:
        query = query.where(Cinema.city.ilike(f"%{city}%"))
    if source:
        query = query.where(Showtime.source == source)
    if booking_mode:
        query = query.where(Showtime.booking_mode == booking_mode)
    if show_date is not None:
        start, end = vietnamese_date_range(show_date)
        query = query.where(
            Showtime.start_time >= start,
            Showtime.start_time < end,
        )
    if upcoming_only:
        query = query.where(Showtime.start_time >= utc_now())
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return [_showtime_read(showtime, room, cinema) for showtime, room, cinema in result]


@router.get("/{showtime_id}", response_model=ShowtimeWithSeats)
async def get_showtime(showtime_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Showtime, CinemaRoom, Cinema)
        .outerjoin(CinemaRoom, Showtime.room_id == CinemaRoom.id)
        .join(Cinema, Showtime.cinema_id == Cinema.id)
        .where(Showtime.id == showtime_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy suất chiếu")
    showtime, room, cinema = row

    inventory_result = await db.execute(
        select(Seat, ShowtimeSeat.status)
        .join(ShowtimeSeat, ShowtimeSeat.seat_id == Seat.id)
        .where(ShowtimeSeat.showtime_id == showtime_id)
        .order_by(Seat.row_label, Seat.col_number)
    )
    inventory_rows = inventory_result.all()
    hold_keys = [
        f"seat_hold:{showtime_id}:{seat.id}" for seat, _status in inventory_rows
    ]
    holders = await redis_client.mget(hold_keys) if hold_keys else []
    seats = []
    for (seat, inventory_status), holder in zip(inventory_rows, holders):
        seat_status = inventory_status.value
        if seat_status == "available" and holder is not None:
            seat_status = "held"
        seats.append(
            SeatRead(
                id=seat.id,
                seat_label=seat.seat_label,
                row_label=seat.row_label,
                col_number=seat.col_number,
                status=seat_status,
            )
        )
    return ShowtimeWithSeats(
        **_showtime_read(showtime, room, cinema).model_dump(), seats=seats
    )


@router.delete("/{showtime_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_showtime(showtime_id: int, db: AsyncSession = Depends(get_db)):
    showtime = await db.get(Showtime, showtime_id)
    if showtime is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy suất chiếu")
    booking_count = await db.scalar(
        select(func.count(Booking.id)).where(Booking.showtime_id == showtime_id)
    )
    if booking_count:
        raise HTTPException(status_code=409, detail="Suất chiếu đã có booking")
    await db.delete(showtime)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Không thể xóa suất chiếu") from exc
