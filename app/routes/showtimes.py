import string

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.movie import Movie
from app.models.seat import Seat
from app.models.showtime import Showtime
from app.schemas.showtime import ShowtimeCreate, ShowtimeRead, ShowtimeWithSeats

router = APIRouter(prefix="/showtimes", tags=["showtimes"])


def _generate_seats(showtime_id: int, rows: int, cols: int) -> list[Seat]:
    """
    Sinh danh sách ghế cho 1 suất chiếu, đặt tên kiểu rạp thật: hàng A-Z, cột 1-N.
    vd rows=5, cols=10 -> A1..A10, B1..B10, ..., E1..E10 (50 ghế).

    Giới hạn 26 hàng vì chỉ có 26 chữ cái A-Z — đã validate ở schema
    (ShowtimeCreate.room_rows có ge=1, le=26).
    """
    seats = []
    for row_idx in range(rows):
        row_label = string.ascii_uppercase[row_idx]
        for col_num in range(1, cols + 1):
            seats.append(
                Seat(
                    showtime_id=showtime_id,
                    seat_label=f"{row_label}{col_num}",
                    row_label=row_label,
                    col_number=col_num,
                )
            )
    return seats


@router.post("", response_model=ShowtimeRead, status_code=status.HTTP_201_CREATED)
async def create_showtime(payload: ShowtimeCreate, db: AsyncSession = Depends(get_db)):
    """
    Tạo suất chiếu mới VÀ tự động sinh toàn bộ ghế tương ứng trong 1 lần gọi.
    Client không cần gọi API riêng để tạo ghế — tránh trường hợp suất chiếu
    tồn tại nhưng thiếu ghế (dữ liệu không nhất quán).
    """
    movie = await db.get(Movie, payload.movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="movie_id không tồn tại")

    showtime = Showtime(**payload.model_dump())
    db.add(showtime)
    await db.flush()  # đẩy INSERT xuống DB để lấy showtime.id, nhưng CHƯA commit
    # (dùng flush thay vì commit ở đây vì ta muốn toàn bộ việc tạo showtime + ghế
    #  nằm trong CÙNG 1 transaction — nếu sinh ghế lỗi giữa chừng, showtime cũng
    #  không được lưu, tránh dữ liệu "suất chiếu không ghế")

    seats = _generate_seats(showtime.id, payload.room_rows, payload.room_cols)
    db.add_all(seats)

    await db.commit()
    await db.refresh(showtime)
    return showtime


@router.get("", response_model=list[ShowtimeRead])
async def list_showtimes(
    movie_id: int | None = None, db: AsyncSession = Depends(get_db)
):
    query = select(Showtime)
    if movie_id is not None:
        query = query.where(Showtime.movie_id == movie_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{showtime_id}", response_model=ShowtimeWithSeats)
async def get_showtime(showtime_id: int, db: AsyncSession = Depends(get_db)):
    """
    Lấy chi tiết 1 suất chiếu KÈM toàn bộ ghế — dùng cho trang chọn ghế.
    selectinload(Showtime.seats): tải sẵn seats trong cùng 1 query, tránh
    lỗi "N+1 query" hoặc lỗi lazy-load trên async session.
    """
    query = (
        select(Showtime)
        .where(Showtime.id == showtime_id)
        .options(selectinload(Showtime.seats))
    )
    result = await db.execute(query)
    showtime = result.scalar_one_or_none()

    if showtime is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy suất chiếu")
    return showtime


@router.delete("/{showtime_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_showtime(showtime_id: int, db: AsyncSession = Depends(get_db)):
    showtime = await db.get(Showtime, showtime_id)
    if showtime is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy suất chiếu")

    await db.delete(showtime)  # ghế liên quan cũng cần xử lý — xem ghi chú README
    await db.commit()
