from datetime import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EventType(str, Enum):
    MOVIE_VIEWED = "movie_viewed"
    MOVIE_SEARCHED = "movie_searched"
    SHOWTIMES_VIEWED = "showtimes_viewed"
    EXTERNAL_BOOKING_CLICKED = "external_booking_clicked"
    PREFERENCE_PROMPT_SUBMITTED = "preference_prompt_submitted"
    RECOMMENDATION_CLICKED = "recommendation_clicked"


class UserEvent(Base):
    __tablename__ = "user_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('movie_viewed', 'movie_searched', "
            "'showtimes_viewed', 'external_booking_clicked', "
            "'preference_prompt_submitted', 'recommendation_clicked')",
            name="ck_user_events_event_type",
        ),
        Index("ix_user_events_user_occurred_at", "user_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    movie_id: Mapped[int | None] = mapped_column(
        ForeignKey("movies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cinema_id: Mapped[int | None] = mapped_column(
        ForeignKey("cinemas.id", ondelete="SET NULL"), nullable=True
    )
    showtime_id: Mapped[int | None] = mapped_column(
        ForeignKey("showtimes.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    search_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    event_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="events")
    movie: Mapped["Movie | None"] = relationship()
    cinema: Mapped["Cinema | None"] = relationship()
    showtime: Mapped["Showtime | None"] = relationship()
