from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CinemaCreate(BaseModel):
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


class CinemaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, min_length=1)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)


class CinemaRead(CinemaCreate):
    id: int
    source: str | None = None
    external_id: str | None = None
    last_synced_at: datetime | None = None
    distance_km: float | None = None
    model_config = ConfigDict(from_attributes=True)


class PhysicalSeatRead(BaseModel):
    id: int
    seat_label: str
    row_label: str
    col_number: int
    model_config = ConfigDict(from_attributes=True)


class CinemaRoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rows: int = Field(default=5, ge=1, le=26)
    cols: int = Field(default=10, ge=1, le=50)


class CinemaRoomUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CinemaRoomRead(BaseModel):
    id: int
    cinema_id: int
    name: str
    seat_count: int
    source: str | None = None
    external_id: str | None = None
    last_synced_at: datetime | None = None


class CinemaRoomDetail(CinemaRoomRead):
    seats: list[PhysicalSeatRead]


class CinemaDetail(CinemaRead):
    rooms: list[CinemaRoomRead]
