from datetime import datetime

from sqlalchemy import ForeignKey, DateTime, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Showtime(Base):
    __tablename__ = "showtimes"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    room_rows: Mapped[int] = mapped_column(Integer, default=5)
    room_cols: Mapped[int] = mapped_column(Integer, default=10)
    price: Mapped[float] = mapped_column(Numeric(10, 2))

    movie: Mapped["Movie"] = relationship(back_populates="showtimes")
    # cascade="all, delete-orphan": xóa 1 Showtime sẽ tự động xóa hết Seat
    # thuộc suất chiếu đó — hợp lý vì ghế của 1 suất chiếu vô nghĩa nếu
    # suất chiếu đó không còn tồn tại.
    seats: Mapped[list["Seat"]] = relationship(
        back_populates="showtime", cascade="all, delete-orphan"
    )
