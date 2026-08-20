from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ProviderMovie(Base):
    """Định danh và metadata phim theo từng nguồn ingestion."""

    __tablename__ = "provider_movies"
    __table_args__ = (
        Index(
            "uq_provider_movies_source_external_id",
            "source",
            "external_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    genres: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    poster_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    movie: Mapped["Movie"] = relationship(back_populates="provider_movies")
    showtimes: Mapped[list["Showtime"]] = relationship(
        back_populates="provider_movie"
    )
