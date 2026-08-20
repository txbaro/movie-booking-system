"""Support internal and external-redirect showtimes.

Revision ID: 20260820_0004
Revises: 20260819_0003
Create Date: 2026-08-20
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260820_0004"
down_revision: str | Sequence[str] | None = "20260819_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("showtimes", sa.Column("cinema_id", sa.Integer(), nullable=True))
    op.add_column(
        "showtimes",
        sa.Column("booking_mode", sa.String(30), nullable=False, server_default="internal"),
    )
    op.add_column(
        "showtimes", sa.Column("external_booking_url", sa.String(2048), nullable=True)
    )
    op.add_column("showtimes", sa.Column("format", sa.String(50), nullable=True))
    op.add_column("showtimes", sa.Column("language", sa.String(100), nullable=True))
    op.create_foreign_key(
        "fk_showtimes_cinema_id_cinemas",
        "showtimes",
        "cinemas",
        ["cinema_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_showtimes_cinema_id", "showtimes", ["cinema_id"])
    op.create_check_constraint(
        "ck_showtimes_booking_mode",
        "showtimes",
        "booking_mode IN ('internal', 'external_redirect')",
    )

    op.execute(
        """
        UPDATE showtimes AS showtime
        SET cinema_id = room.cinema_id
        FROM cinema_rooms AS room
        WHERE showtime.room_id = room.id
        """
    )
    bind = op.get_bind()
    missing = bind.execute(
        sa.text("SELECT count(*) FROM showtimes WHERE cinema_id IS NULL")
    ).scalar_one()
    if missing:
        raise RuntimeError(f"cannot backfill cinema_id for {missing} showtimes")

    op.alter_column("showtimes", "cinema_id", nullable=False)
    op.alter_column("showtimes", "price", existing_type=sa.Numeric(10, 2), nullable=True)
    op.alter_column("showtimes", "booking_mode", server_default=None)


def downgrade() -> None:
    external_count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM showtimes WHERE room_id IS NULL OR price IS NULL")
    ).scalar_one()
    if external_count:
        raise RuntimeError("cannot downgrade while external showtimes exist")

    op.alter_column("showtimes", "price", existing_type=sa.Numeric(10, 2), nullable=False)
    op.drop_constraint("ck_showtimes_booking_mode", "showtimes", type_="check")
    op.drop_index("ix_showtimes_cinema_id", table_name="showtimes")
    op.drop_constraint("fk_showtimes_cinema_id_cinemas", "showtimes", type_="foreignkey")
    op.drop_column("showtimes", "language")
    op.drop_column("showtimes", "format")
    op.drop_column("showtimes", "external_booking_url")
    op.drop_column("showtimes", "booking_mode")
    op.drop_column("showtimes", "cinema_id")
