from sqlalchemy import Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.seat import SeatStatus


class ShowtimeSeat(Base):
    """Trạng thái của một ghế vật lý trong phạm vi một suất chiếu.

    Một ``Seat`` có thể được tái sử dụng bởi nhiều suất chiếu trong cùng
    phòng, nhưng mỗi cặp (showtime, seat) chỉ có đúng một trạng thái. Model
    này được thêm song song với schema cũ; booking flow sẽ chuyển sang sử
    dụng nó sau khi dữ liệu hiện tại đã được backfill.
    """

    __tablename__ = "showtime_seats"
    __table_args__ = (
        UniqueConstraint(
            "showtime_id",
            "seat_id",
            name="uq_showtime_seat_inventory",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    showtime_id: Mapped[int] = mapped_column(
        ForeignKey("showtimes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seat_id: Mapped[int] = mapped_column(
        ForeignKey("seats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[SeatStatus] = mapped_column(
        Enum(SeatStatus),
        default=SeatStatus.AVAILABLE,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    showtime: Mapped["Showtime"] = relationship(back_populates="showtime_seats")
    seat: Mapped["Seat"] = relationship(back_populates="showtime_seats")
    booking_seat: Mapped["BookingSeat | None"] = relationship(
        back_populates="showtime_seat",
        uselist=False,
    )
