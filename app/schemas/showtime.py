from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ShowtimeCreate(BaseModel):
    movie_id: int
    start_time: datetime
    room_rows: int = Field(default=5, ge=1, le=26)  # tối đa 26 vì dùng A-Z làm tên hàng
    room_cols: int = Field(default=10, ge=1, le=50)
    price: Decimal


class ShowtimeRead(BaseModel):
    id: int
    movie_id: int
    start_time: datetime
    room_rows: int
    room_cols: int
    price: Decimal

    model_config = ConfigDict(from_attributes=True)


class SeatRead(BaseModel):
    """
    Dùng khi trả về sơ đồ ghế cho 1 suất chiếu — client (FE) sẽ dùng
    row_label + col_number để vẽ lưới ghế, và status để tô màu ghế
    đã đặt/còn trống.
    """
    id: int
    seat_label: str
    row_label: str
    col_number: int
    status: str

    model_config = ConfigDict(from_attributes=True)


class ShowtimeWithSeats(ShowtimeRead):
    """Dùng cho trang chọn ghế — trả kèm luôn toàn bộ danh sách ghế."""
    seats: list[SeatRead] = []
