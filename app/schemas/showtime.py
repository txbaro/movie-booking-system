from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ShowtimeCreate(BaseModel):
    movie_id: int
    room_id: int
    start_time: datetime
    price: Decimal = Field(gt=0)


class ShowtimeRead(BaseModel):
    id: int
    movie_id: int
    room_id: int | None
    room_name: str | None
    cinema_id: int
    cinema_name: str
    city: str
    start_time: datetime
    price: Decimal | None
    booking_mode: str
    external_booking_url: str | None = None
    format: str | None = None
    language: str | None = None
    source: str | None = None
    external_id: str | None = None
    last_synced_at: datetime | None = None

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
    seats: list[SeatRead] = Field(default_factory=list)
