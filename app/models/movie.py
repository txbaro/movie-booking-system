from sqlalchemy import String, Text, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    # Thể loại lưu dạng "Action,Sci-Fi,Thriller" — đơn giản cho MVP.
    # Nếu sau này cần query phức tạp hơn, có thể tách thành bảng riêng (many-to-many).
    genres: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    poster_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)

    showtimes: Mapped[list["Showtime"]] = relationship(back_populates="movie")
