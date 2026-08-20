"""Booking nhiều ghế với Redis hold và PostgreSQL row-level locking."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.redis_client import redis_client
from app.core.ws_manager import manager
from app.models.booking import Booking
from app.models.booking_seat import BookingSeat
from app.models.movie import Movie
from app.models.seat import Seat, SeatStatus
from app.models.showtime import BookingMode, Showtime
from app.models.showtime_seat import ShowtimeSeat
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingRead, BookingSeatRead

router = APIRouter(prefix="/bookings", tags=["bookings"])

SEAT_HOLD_TTL_SECONDS = 300
MAX_SEATS_PER_BOOKING = 10


def _hold_key(showtime_id: int, seat_id: int) -> str:
    return f"seat_hold:{showtime_id}:{seat_id}"


def _user_holds_key(user_id: int, showtime_id: int) -> str:
    return f"user_holds:{user_id}:{showtime_id}"


async def _get_inventory(
    db: AsyncSession, showtime_id: int, seat_id: int
) -> ShowtimeSeat | None:
    result = await db.execute(
        select(ShowtimeSeat).where(
            ShowtimeSeat.showtime_id == showtime_id,
            ShowtimeSeat.seat_id == seat_id,
        )
    )
    return result.scalar_one_or_none()


async def _get_bookings_with_details(db: AsyncSession, *filters) -> list[BookingRead]:
    query = (
        select(Booking, Movie.title, Seat.id, Seat.seat_label)
        .join(Showtime, Booking.showtime_id == Showtime.id)
        .join(Movie, Showtime.movie_id == Movie.id)
        .join(BookingSeat, BookingSeat.booking_id == Booking.id)
        .join(ShowtimeSeat, ShowtimeSeat.id == BookingSeat.showtime_seat_id)
        .join(Seat, Seat.id == ShowtimeSeat.seat_id)
        .order_by(Booking.id.desc(), Seat.row_label, Seat.col_number)
    )
    if filters:
        query = query.where(*filters)

    rows = (await db.execute(query)).all()
    grouped: dict[int, BookingRead] = {}
    for booking, movie_title, seat_id, seat_label in rows:
        item = grouped.get(booking.id)
        if item is None:
            item = BookingRead(
                id=booking.id,
                user_id=booking.user_id,
                showtime_id=booking.showtime_id,
                movie_title=movie_title,
                seats=[],
                booked_at=booking.booked_at,
            )
            grouped[booking.id] = item
        item.seats.append(BookingSeatRead(seat_id=seat_id, seat_label=seat_label))
    return list(grouped.values())


@router.post("/hold/{showtime_id}/{seat_id}", status_code=status.HTTP_200_OK)
async def hold_seat(
    showtime_id: int,
    seat_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    showtime = await db.get(Showtime, showtime_id)
    if showtime is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy suất chiếu")
    if showtime.booking_mode != BookingMode.INTERNAL.value:
        raise HTTPException(
            status_code=409,
            detail="Suất chiếu này được đặt vé tại website của nhà cung cấp",
        )
    inventory = await _get_inventory(db, showtime_id, seat_id)
    if inventory is None:
        raise HTTPException(status_code=404, detail="Ghế không thuộc suất chiếu này")
    if inventory.status != SeatStatus.AVAILABLE:
        raise HTTPException(status_code=409, detail="Ghế này đã được đặt")

    hold_key = _hold_key(showtime_id, seat_id)
    user_key = _user_holds_key(current_user.id, showtime_id)
    holder_id = await redis_client.get(hold_key)
    if holder_id not in (None, str(current_user.id)):
        raise HTTPException(status_code=409, detail="Ghế đang được người khác giữ")

    held_seat_ids = await redis_client.smembers(user_key)
    for held_seat_id in held_seat_ids:
        if not await redis_client.exists(_hold_key(showtime_id, int(held_seat_id))):
            await redis_client.srem(user_key, held_seat_id)

    if not holder_id and await redis_client.scard(user_key) >= MAX_SEATS_PER_BOOKING:
        raise HTTPException(
            status_code=409,
            detail=f"Chỉ được giữ tối đa {MAX_SEATS_PER_BOOKING} ghế",
        )

    acquired = await redis_client.set(
        hold_key,
        str(current_user.id),
        nx=holder_id is None,
        ex=SEAT_HOLD_TTL_SECONDS,
    )
    if not acquired:
        raise HTTPException(status_code=409, detail="Ghế đang được người khác giữ")

    await redis_client.sadd(user_key, seat_id)
    await redis_client.expire(user_key, SEAT_HOLD_TTL_SECONDS)
    await manager.broadcast(
        showtime_id,
        {"type": "seat_update", "seat_id": seat_id, "status": "held"},
    )
    return {
        "message": "Đã giữ ghế",
        "showtime_id": showtime_id,
        "seat_id": seat_id,
        "hold_expires_in_seconds": SEAT_HOLD_TTL_SECONDS,
    }


@router.delete(
    "/hold/{showtime_id}/{seat_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def release_hold(
    showtime_id: int,
    seat_id: int,
    current_user: User = Depends(get_current_user),
):
    key = _hold_key(showtime_id, seat_id)
    if await redis_client.get(key) == str(current_user.id):
        await redis_client.delete(key)
        await redis_client.srem(_user_holds_key(current_user.id, showtime_id), seat_id)
        await manager.broadcast(
            showtime_id,
            {"type": "seat_update", "seat_id": seat_id, "status": "available"},
        )


@router.get("/holds/{showtime_id}")
async def get_my_holds(
    showtime_id: int,
    current_user: User = Depends(get_current_user),
):
    user_key = _user_holds_key(current_user.id, showtime_id)
    seat_ids = await redis_client.smembers(user_key)
    holds = []
    for raw_seat_id in seat_ids:
        seat_id = int(raw_seat_id)
        key = _hold_key(showtime_id, seat_id)
        holder_id = await redis_client.get(key)
        ttl = await redis_client.ttl(key)
        if holder_id == str(current_user.id) and ttl > 0:
            holds.append({"seat_id": seat_id, "expires_in_seconds": ttl})
        else:
            await redis_client.srem(user_key, raw_seat_id)
    return sorted(holds, key=lambda item: item["seat_id"])


@router.post("", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    showtime = await db.get(Showtime, payload.showtime_id)
    if showtime is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy suất chiếu")
    if showtime.booking_mode != BookingMode.INTERNAL.value:
        raise HTTPException(
            status_code=409,
            detail="Suất chiếu này được đặt vé tại website của nhà cung cấp",
        )
    seat_ids = sorted(payload.seat_ids)
    result = await db.execute(
        select(ShowtimeSeat)
        .where(
            ShowtimeSeat.showtime_id == payload.showtime_id,
            ShowtimeSeat.seat_id.in_(seat_ids),
        )
        .order_by(ShowtimeSeat.seat_id)
        .with_for_update()
    )
    inventory = result.scalars().all()

    if len(inventory) != len(seat_ids):
        raise HTTPException(status_code=404, detail="Có ghế không thuộc suất chiếu")
    if any(item.status != SeatStatus.AVAILABLE for item in inventory):
        raise HTTPException(status_code=409, detail="Có ghế vừa được người khác đặt")

    for seat_id in seat_ids:
        holder_id = await redis_client.get(_hold_key(payload.showtime_id, seat_id))
        if holder_id is not None and holder_id != str(current_user.id):
            raise HTTPException(status_code=409, detail=f"Ghế {seat_id} đang được giữ")

    booking = Booking(
        user_id=current_user.id,
        showtime_id=payload.showtime_id,
        seat_id=None,
    )
    db.add(booking)
    await db.flush()

    for item in inventory:
        item.status = SeatStatus.BOOKED
        item.version += 1
        db.add(BookingSeat(booking_id=booking.id, showtime_seat_id=item.id))

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="Một hoặc nhiều ghế vừa được đặt"
        ) from exc

    hold_keys = [_hold_key(payload.showtime_id, seat_id) for seat_id in seat_ids]
    await redis_client.delete(*hold_keys)
    await redis_client.delete(_user_holds_key(current_user.id, payload.showtime_id))
    for seat_id in seat_ids:
        await manager.broadcast(
            payload.showtime_id,
            {"type": "seat_update", "seat_id": seat_id, "status": "booked"},
        )

    bookings = await _get_bookings_with_details(db, Booking.id == booking.id)
    return bookings[0]


@router.get("/me", response_model=list[BookingRead])
async def get_my_bookings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_bookings_with_details(db, Booking.user_id == current_user.id)
