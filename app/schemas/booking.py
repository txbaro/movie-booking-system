from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BookingCreate(BaseModel):
    seat_id: int


class BookingRead(BaseModel):
    id: int
    user_id: int
    showtime_id: int
    seat_id: int
    booked_at: datetime

    model_config = ConfigDict(from_attributes=True)