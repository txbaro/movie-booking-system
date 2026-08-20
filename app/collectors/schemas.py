from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CollectedCinema(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1)
    city: str = Field(min_length=1, max_length=100)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def coordinates_must_be_a_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude và longitude phải cùng có hoặc cùng thiếu")
        return self


class CollectedRoom(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=100)
    rows: int = Field(ge=1, le=26)
    cols: int = Field(ge=1, le=50)


class CollectedMovie(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    genres: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    duration_minutes: int = Field(gt=0)
    rating: float = Field(default=0.0, ge=0, le=10)
    poster_url: str | None = None


class CollectedShowtime(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    cinema: CollectedCinema
    room: CollectedRoom | None = None
    movie: CollectedMovie
    start_time: datetime
    price: Decimal | None = Field(default=None, gt=0)
    booking_mode: Literal["internal", "external_redirect"] = "internal"
    external_booking_url: str | None = Field(
        default=None, min_length=1, max_length=2048
    )
    format: str | None = Field(default=None, max_length=50)
    language: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def start_time_must_have_timezone(self):
        if self.start_time.tzinfo is None:
            raise ValueError("start_time phải chứa timezone")
        if self.booking_mode == "internal":
            if self.room is None or self.price is None:
                raise ValueError("suất nội bộ phải có room và price")
            if self.external_booking_url is not None:
                raise ValueError("suất nội bộ không dùng external_booking_url")
        elif not self.external_booking_url:
            raise ValueError("suất external phải có external_booking_url")
        return self
