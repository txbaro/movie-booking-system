from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BookingMode(str, Enum):
    INTERNAL = "internal"
    EXTERNAL_REDIRECT = "external_redirect"


class Showtime(Base):
    __tablename__ = "showtimes"
    __table_args__ = (
        Index(
            "uq_showtimes_source_external_id",
            "source",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        CheckConstraint(
            "booking_mode IN ('internal', 'external_redirect')",
            name="ck_showtimes_booking_mode",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"), index=True)
    provider_movie_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_movies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cinema_id: Mapped[int] = mapped_column(
        ForeignKey("cinemas.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    room_id: Mapped[int | None] = mapped_column(
        ForeignKey("cinema_rooms.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    room_rows: Mapped[int] = mapped_column(Integer, default=5)
    room_cols: Mapped[int] = mapped_column(Integer, default=10)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    booking_mode: Mapped[str] = mapped_column(
        String(30), nullable=False, default=BookingMode.INTERNAL.value
    )
    external_booking_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    movie: Mapped["Movie"] = relationship(back_populates="showtimes")
    provider_movie: Mapped["ProviderMovie | None"] = relationship(
        back_populates="showtimes"
    )
    cinema: Mapped["Cinema"] = relationship(back_populates="showtimes")
    room: Mapped["CinemaRoom | None"] = relationship(back_populates="showtimes")
    # cascade="all, delete-orphan": xóa 1 Showtime sẽ tự động xóa hết Seat
    # thuộc suất chiếu đó — hợp lý vì ghế của 1 suất chiếu vô nghĩa nếu
    # suất chiếu đó không còn tồn tại.
    seats: Mapped[list["Seat"]] = relationship(
        back_populates="showtime", cascade="all, delete-orphan"
    )
    # Inventory theo từng suất chiếu của architecture mới. Relationship cũ
    # ``seats`` vẫn được giữ trong giai đoạn chuyển tiếp để API hiện tại chạy.
    showtime_seats: Mapped[list["ShowtimeSeat"]] = relationship(
        back_populates="showtime",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
