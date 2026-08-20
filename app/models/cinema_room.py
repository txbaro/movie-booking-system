from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CinemaRoom(Base):
    __tablename__ = "cinema_rooms"
    __table_args__ = (
        UniqueConstraint("cinema_id", "name", name="uq_cinema_room_name"),
        Index(
            "uq_cinema_rooms_source_external_id",
            "source",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    cinema_id: Mapped[int] = mapped_column(
        ForeignKey("cinemas.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(100))
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    cinema: Mapped["Cinema"] = relationship(back_populates="rooms")
    # Trong STEP 2, Seat đồng thời còn thuộc Showtime để giữ tương thích với
    # booking flow cũ. Chưa dùng delete-orphan ở đây: xóa một phòng trong giai
    # đoạn chuyển tiếp không được phép vô tình xóa inventory đang hoạt động.
    seats: Mapped[list["Seat"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )
    showtimes: Mapped[list["Showtime"]] = relationship(back_populates="room")
