from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BookingSeat(Base):
    """Một ghế của một booking trong inventory của suất chiếu.

    Bảng nối này thay thế dần ``Booking.seat_id`` và cho phép một booking có
    nhiều ghế. Ràng buộc unique trên ``showtime_seat_id`` là lớp bảo vệ cuối
    cùng ở database: một inventory seat không thể thuộc hai booking.
    """

    __tablename__ = "booking_seats"
    __table_args__ = (
        UniqueConstraint(
            "showtime_seat_id",
            name="uq_booking_showtime_seat",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    showtime_seat_id: Mapped[int] = mapped_column(
        ForeignKey("showtime_seats.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    booking: Mapped["Booking"] = relationship(back_populates="booking_seats")
    showtime_seat: Mapped["ShowtimeSeat"] = relationship(
        back_populates="booking_seat"
    )
