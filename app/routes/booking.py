"""
Luồng đặt vé với 2 lớp bảo vệ chống double-booking:

LỚP 1 - Redis (giữ ghế tạm thời, TTL 10 phút):
  Khi user "chọn" ghế (trước khi thanh toán), ta cố giành 1 "khóa mềm"
  trong Redis. Khóa này tự động hết hạn nếu user không thanh toán kịp,
  không cần code dọn dẹp thủ công (đây là điểm mạnh chính của Redis
  so với việc tự làm bằng PostgreSQL - xem lại phần đã thảo luận).

LỚP 2 - PostgreSQL SELECT ... FOR UPDATE (xác nhận booking cuối cùng):
  Đây mới là "sự thật" cuối cùng. Dù Redis đã giữ ghế, vẫn LUÔN xác nhận
  lại bằng transaction locking ở tầng DB trước khi ghi booking thật -
  không bao giờ tin tưởng tuyệt đối chỉ 1 lớp bảo vệ duy nhất.

LUỒNG SỬ DỤNG THỰC TẾ (giống hầu hết app đặt vé):
  1. User bấm chọn ghế -> POST /bookings/hold/{seat_id}  (giữ 10 phút)
  2. User điền thông tin thanh toán... (thời gian trôi qua)
  3. User bấm "Xác nhận" -> POST /bookings  (chốt booking thật)
     hoặc
     User đổi ý / rời trang -> DELETE /bookings/hold/{seat_id}  (nhả ghế sớm)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.redis_client import redis_client
from app.models.booking import Booking
from app.models.seat import Seat, SeatStatus
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingRead

router = APIRouter(prefix="/bookings", tags=["bookings"])

SEAT_HOLD_TTL_SECONDS = 600  # 10 phút


def _hold_key(seat_id: int) -> str:
    """Tên key Redis dùng cho việc giữ ghế — tách hàm riêng để không gõ sai ở nhiều chỗ."""
    return f"seat_hold:{seat_id}"


@router.post("/hold/{seat_id}", status_code=status.HTTP_200_OK)
async def hold_seat(
    seat_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Giữ ghế tạm thời 10 phút cho user hiện tại.

    set(..., nx=True): NX = "only set if Not eXists" — đây là điểm mấu chốt
    để thao tác này AN TOÀN với concurrency. Nếu 2 request gọi hàm này gần
    như đồng thời cho CÙNG 1 seat_id, Redis đảm bảo chỉ 1 request set
    thành công (trả True), request kia nhận False NGAY LẬP TỨC - không
    có khoảng hở race condition nào ở đây, vì Redis xử lý lệnh này
    NGUYÊN TỬ (atomic), không thể bị "chen ngang" giữa chừng.
    """
    seat = await db.get(Seat, seat_id)
    if seat is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy ghế")
    if seat.status != SeatStatus.AVAILABLE:
        raise HTTPException(status_code=409, detail="Ghế này đã được đặt")

    acquired = await redis_client.set(
        _hold_key(seat_id), str(current_user.id), nx=True, ex=SEAT_HOLD_TTL_SECONDS
    )
    if not acquired:
        raise HTTPException(
            status_code=409, detail="Ghế đang được người khác giữ, thử ghế khác"
        )

    return {
        "message": "Đã giữ ghế",
        "seat_id": seat_id,
        "hold_expires_in_seconds": SEAT_HOLD_TTL_SECONDS,
    }


@router.delete("/hold/{seat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def release_hold(
    seat_id: int, current_user: User = Depends(get_current_user)
):
    """
    Chủ động nhả ghế trước khi hết hạn 10 phút (vd user đổi ý, chọn ghế khác).
    Chỉ người ĐANG giữ ghế đó mới nhả được - tránh user A vô tình/cố ý nhả
    ghế đang được user B giữ.
    """
    key = _hold_key(seat_id)
    holder_id = await redis_client.get(key)

    if holder_id == str(current_user.id):
        await redis_client.delete(key)
    # Nếu không phải chủ khóa hoặc khóa đã hết hạn tự nhiên: coi như thành
    # công luôn (không raise lỗi) - vì kết quả cuối cùng người dùng mong
    # muốn ("ghế không còn bị tôi giữ nữa") đã đúng trong mọi trường hợp.


@router.post("", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Xác nhận booking cuối cùng - LỚP 2, dùng PostgreSQL transaction locking.

    with_for_update(): khóa dòng Seat này ngay lúc SELECT. Nếu có request
    khác đang giữ khóa trên CÙNG dòng, request hiện tại phải CHỜ (không đọc
    được) cho tới khi request kia commit/rollback xong. Đây chính là cách
    loại bỏ khoảng hở "đọc xong nhưng chưa kịp ghi" đã gây ra bug ở Task 6.
    """
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
        # LỚP BẢO HIỂM cuối cùng: dù with_for_update() đã ngăn race condition
        # trong hầu hết trường hợp, vẫn bọc try/except quanh commit() phòng
        # edge case hiếm gặp - không để lỗi 500 mơ hồ lọt ra như Task 6.
        await db.rollback()
        raise HTTPException(status_code=409, detail="Ghế này vừa có người đặt")

    await db.refresh(booking)

    # Booking đã chốt thật trong DB -> không cần giữ khóa Redis tạm thời nữa,
    # dọn luôn để trả lại tài nguyên (dù không dọn, key này cũng tự hết hạn
    # sau 10 phút, nhưng dọn ngay giúp trạng thái nhất quán sớm hơn).
    await redis_client.delete(_hold_key(payload.seat_id))

    return booking


@router.get("/me", response_model=list[BookingRead])
async def get_my_bookings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Booking).where(Booking.user_id == current_user.id)
    )
    return result.scalars().all()