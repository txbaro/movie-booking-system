from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BookingCreate(BaseModel):
    showtime_id: int
    seat_ids: list[int] = Field(min_length=1, max_length=10)

    @field_validator("seat_ids")
    @classmethod
    def seat_ids_must_be_unique(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("seat_ids không được trùng nhau")
        return value


class BookingSeatRead(BaseModel):
    seat_id: int
    seat_label: str


class BookingRead(BaseModel):
    id: int
    user_id: int
    showtime_id: int
    movie_title: str
    seats: list[BookingSeatRead]
    booked_at: datetime

    model_config = ConfigDict(from_attributes=True)
