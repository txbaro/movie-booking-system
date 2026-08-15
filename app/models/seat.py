import enum

from sqlalchemy import ForeignKey, String, Enum, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SeatStatus(str, enum.Enum):
    AVAILABLE = "available"
    BOOKED = "booked"


class Seat(Base):
    """
    Mỗi Showtime có bộ ghế RIÊNG (không dùng chung ghế giữa các suất chiếu),
    vì trạng thái "đã đặt" chỉ có ý nghĩa trong phạm vi 1 suất chiếu cụ thể.

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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    showtime_id: Mapped[int] = mapped_column(ForeignKey("showtimes.id"))
    seat_label: Mapped[str] = mapped_column(String(10))  # vd: "A5", "C10"
    row_label: Mapped[str] = mapped_column(String(5))
    col_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[SeatStatus] = mapped_column(
        Enum(SeatStatus), default=SeatStatus.AVAILABLE
    )
    # Optimistic locking version — xem giải thích ở docstring trên
    version: Mapped[int] = mapped_column(Integer, default=0)

    showtime: Mapped["Showtime"] = relationship(back_populates="seats")
    # cascade: khi Booking bị xóa, không tự xóa Seat (ghế vẫn tồn tại,
    # chỉ là không còn ai đặt) — nên KHÔNG đặt cascade ở đây, chỉ đặt
    # ở phía Showtime -> Seat (xem app/models/showtime.py)
    booking: Mapped["Booking"] = relationship(back_populates="seat", uselist=False)
