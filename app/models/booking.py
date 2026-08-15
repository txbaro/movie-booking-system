from datetime import datetime

from sqlalchemy import ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    showtime_id: Mapped[int] = mapped_column(ForeignKey("showtimes.id"))
    # unique=True => 1 ghế chỉ có thể gắn với TỐI ĐA 1 booking.
    # Đây là ràng buộc DB-level thứ hai bảo vệ chống double-booking.
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id"), unique=True)
    booked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="bookings")
    seat: Mapped["Seat"] = relationship(back_populates="booking")
