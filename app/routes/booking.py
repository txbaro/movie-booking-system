"""
Luồng đặt vé với 2 lớp bảo vệ chống double-booking:

LỚP 1 - Redis (giữ ghế tạm thời, TTL 10 phút):
LỚP 2 - PostgreSQL SELECT ... FOR UPDATE (xác nhận booking cuối cùng):

RÀNG BUỘC "1 USER CHỈ GIỮ TỐI ĐA 1 GHẾ" (chống spam/hoarding):
  Dùng thêm key Redis phụ `user_hold:{user_id}` trỏ NGƯỢC lại ghế user đó
  đang giữ. Khi user cố giữ ghế MỚI, server TỰ ĐỘNG nhả ghế cũ (nếu có)
  TRƯỚC khi cho giữ ghế mới - ép buộc ở tầng SERVER, không phụ thuộc vào
  việc client (JS) có gọi đúng thứ tự hay không. Điều này chặn được cả
  trường hợp ai đó bỏ qua giao diện, gọi thẳng API để giữ nhiều ghế cùng lúc.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.redis_client import redis_client
from app.models.booking import Booking
from app.models.movie import Movie
from app.models.seat import Seat, SeatStatus
from app.models.showtime import Showtime
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingRead

router = APIRouter(prefix="/bookings", tags=["bookings"])

SEAT_HOLD_TTL_SECONDS = 600  # 10 phút


def _hold_key(seat_id: int) -> str:
    return f"seat_hold:{seat_id}"


def _user_hold_key(user_id: int) -> str:
    """Key phụ, trỏ NGƯỢC user -> ghế đang giữ. Dùng để enforce '1 user = 1 ghế'."""
    return f"user_hold:{user_id}"


async def _release_previous_hold(user_id: int) -> None:
    """
    Nếu user đang giữ 1 ghế khác từ trước, nhả nó ra trước khi cho giữ
    ghế mới. Đây là bước then chốt chống spam - CHẠY Ở SERVER, không thể
    bị bỏ qua bởi client.
    """
    user_key = _user_hold_key(user_id)
    previous_seat_id = await redis_client.get(user_key)
    if previous_seat_id is not None:
        await redis_client.delete(_hold_key(int(previous_seat_id)))
        await redis_client.delete(user_key)


async def _get_bookings_with_details(db: AsyncSession, *filters) -> list[BookingRead]:
    query = (
        select(Booking, Seat.seat_label, Movie.title)
        .join(Seat, Booking.seat_id == Seat.id)
        .join(Showtime, Seat.showtime_id == Showtime.id)
        .join(Movie, Showtime.movie_id == Movie.id)
    )
    if filters:
        query = query.where(*filters)

    result = await db.execute(query)
    bookings = []
    for booking_obj, seat_label, movie_title in result.all():
        bookings.append(
            BookingRead(
                id=booking_obj.id, user_id=booking_obj.user_id,
                showtime_id=booking_obj.showtime_id, seat_id=booking_obj.seat_id,
                seat_label=seat_label, movie_title=movie_title,
                booked_at=booking_obj.booked_at,
            )
        )
    return bookings


@router.post("/hold/{seat_id}", status_code=status.HTTP_200_OK)
async def hold_seat(
    seat_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    seat = await db.get(Seat, seat_id)
    if seat is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy ghế")
    if seat.status != SeatStatus.AVAILABLE:
        raise HTTPException(status_code=409, detail="Ghế này đã được đặt")

    # Chặn spam: tự nhả ghế cũ (nếu có) của CHÍNH user này trước khi giữ
    # ghế mới - đảm bảo mỗi user chỉ giữ được tối đa 1 ghế tại 1 thời điểm,
    # bất kể họ gọi API bao nhiêu lần hay theo thứ tự nào.
    await _release_previous_hold(current_user.id)

    acquired = await redis_client.set(
        _hold_key(seat_id), str(current_user.id), nx=True, ex=SEAT_HOLD_TTL_SECONDS
    )
    if not acquired:
        raise HTTPException(
            status_code=409, detail="Ghế đang được người khác giữ, thử ghế khác"
        )

    # Ghi lại "user này đang giữ ghế nào" để lần sau còn biết mà nhả
    await redis_client.set(
        _user_hold_key(current_user.id), str(seat_id), ex=SEAT_HOLD_TTL_SECONDS
    )

    return {
        "message": "Đã giữ ghế", "seat_id": seat_id,
        "hold_expires_in_seconds": SEAT_HOLD_TTL_SECONDS,
    }


@router.delete("/hold/{seat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def release_hold(seat_id: int, current_user: User = Depends(get_current_user)):
    key = _hold_key(seat_id)
    holder_id = await redis_client.get(key)
    if holder_id == str(current_user.id):
        await redis_client.delete(key)
        await redis_client.delete(_user_hold_key(current_user.id))


@router.post("", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Seat).where(Seat.id == payload.seat_id).with_for_update()
    )
    seat = result.scalar_one_or_none()

    if seat is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy ghế")
    if seat.status != SeatStatus.AVAILABLE:
        raise HTTPException(status_code=409, detail="Ghế này đã có người đặt")

    booking = Booking(
        user_id=current_user.id, showtime_id=seat.showtime_id, seat_id=seat.id
    )
    seat.status = SeatStatus.BOOKED
    db.add(booking)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Ghế này vừa có người đặt")

    await redis_client.delete(_hold_key(payload.seat_id))
    await redis_client.delete(_user_hold_key(current_user.id))

    bookings = await _get_bookings_with_details(db, Booking.id == booking.id)
    return bookings[0]


@router.get("/me", response_model=list[BookingRead])
async def get_my_bookings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_bookings_with_details(db, Booking.user_id == current_user.id)