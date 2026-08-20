import enum

from sqlalchemy import ForeignKey, String, Enum, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SeatStatus(str, enum.Enum):
    AVAILABLE = "available"
    BOOKED = "booked"


class Seat(Base):
    """
    Model chuyển tiếp của STEP 2.

    Ghế vật lý bắt đầu được liên kết với CinemaRoom qua ``room_id``. Liên kết
    cũ tới Showtime vẫn được giữ để booking flow hiện tại tiếp tục hoạt động
    cho tới khi có ShowtimeSeat ở bước kế tiếp. Vì dữ liệu cũ chưa được
    backfill, ``room_id`` tạm thời cho phép NULL.

    Đây là bảng quan trọng nhất cho việc xử lý conflict:
    - `version`: dùng cho OPTIMISTIC LOCKING — mỗi lần update, version tăng lên 1.
      Nếu 2 request cùng đọc version=1 rồi cùng cố update, chỉ 1 cái thành công
      (vì sau khi cái đầu tiên commit, version đã thành 2, cái thứ hai sẽ fail).
    - Ngoài ra route booking sẽ dùng SELECT ... FOR UPDATE (pessimistic locking)
      để khóa row này trong lúc xử lý — xem app/routes/booking.py
    """
    __tablename__ = "seats"
    __table_args__ = (
        # Đảm bảo ở tầng DATABASE (không chỉ ở code) rằng không có 2 ghế
        # trùng label trong cùng 1 suất chiếu — lớp bảo vệ cuối cùng.
        UniqueConstraint("showtime_id", "seat_label", name="uq_showtime_seat"),
        UniqueConstraint("room_id", "seat_label", name="uq_room_seat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int | None] = mapped_column(
        ForeignKey("cinema_rooms.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    showtime_id: Mapped[int | None] = mapped_column(
        ForeignKey("showtimes.id"), nullable=True
    )
    seat_label: Mapped[str] = mapped_column(String(10))  # vd: "A5", "C10"
    row_label: Mapped[str] = mapped_column(String(5))
    col_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[SeatStatus] = mapped_column(
        Enum(SeatStatus), default=SeatStatus.AVAILABLE
    )
    # Optimistic locking version — xem giải thích ở docstring trên
    version: Mapped[int] = mapped_column(Integer, default=0)

    room: Mapped["CinemaRoom | None"] = relationship(back_populates="seats")
    showtime: Mapped["Showtime | None"] = relationship(back_populates="seats")
    showtime_seats: Mapped[list["ShowtimeSeat"]] = relationship(
        back_populates="seat",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # cascade: khi Booking bị xóa, không tự xóa Seat (ghế vẫn tồn tại,
    # chỉ là không còn ai đặt) — nên KHÔNG đặt cascade ở đây, chỉ đặt
    # ở phía Showtime -> Seat (xem app/models/showtime.py)
    booking: Mapped["Booking | None"] = relationship(
        back_populates="seat",
        uselist=False,
    )
