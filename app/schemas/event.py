from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


EventName = Literal[
    "movie_viewed",
    "movie_searched",
    "showtimes_viewed",
    "external_booking_clicked",
    "preference_prompt_submitted",
    "recommendation_clicked",
]


class UserEventCreate(BaseModel):
    event_type: EventName
    movie_id: int | None = Field(default=None, gt=0)
    showtime_id: int | None = Field(default=None, gt=0)
    search_query: str | None = Field(default=None, max_length=1000)
    context_id: str | None = Field(default=None, min_length=36, max_length=36)

    @model_validator(mode="after")
    def validate_event_context(self):
        if self.event_type in {
            "movie_viewed",
            "showtimes_viewed",
            "recommendation_clicked",
        }:
            if self.movie_id is None:
                raise ValueError(f"{self.event_type} yêu cầu movie_id")
            if self.event_type == "recommendation_clicked" and not self.context_id:
                raise ValueError("recommendation_clicked yêu cầu context_id")
        elif self.event_type == "external_booking_clicked":
            if self.showtime_id is None:
                raise ValueError("external_booking_clicked yêu cầu showtime_id")
        elif not self.search_query or not self.search_query.strip():
            raise ValueError(f"{self.event_type} yêu cầu search_query")
        return self


class UserEventRead(BaseModel):
    id: int
    user_id: int
    event_type: str
    movie_id: int | None
    cinema_id: int | None
    showtime_id: int | None
    source: str | None
    search_query: str | None
    context_id: str | None
    event_data: dict | None
    occurred_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TrackEventResponse(BaseModel):
    event: UserEventRead
    deduplicated: bool
