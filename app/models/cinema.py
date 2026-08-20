from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Cinema(Base):
    __tablename__ = "cinemas"
    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="ck_cinemas_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="ck_cinemas_longitude",
        ),
        Index(
            "uq_cinemas_source_external_id",
            "source",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(100))
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    rooms: Mapped[list["CinemaRoom"]] = relationship(
        back_populates="cinema",
        cascade="all, delete-orphan",
    )
    showtimes: Mapped[list["Showtime"]] = relationship(back_populates="cinema")
