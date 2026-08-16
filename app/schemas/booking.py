from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BookingCreate(BaseModel):
    seat_id: int


class BookingRead(BaseModel):
    id: int
    user_id: int
    showtime_id: int
    seat_id: int
    seat_label: str    # vd "A5" — lấy qua join, không phải attribute trực tiếp của Booking
    movie_title: str    # vd "Inception" — lấy qua join Seat -> Showtime -> Movie
    booked_at: datetime

    model_config = ConfigDict(from_attributes=True)