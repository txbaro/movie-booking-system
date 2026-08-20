"""Allow physical seats to exist independently from showtimes.

Revision ID: 20260819_0002
Revises: 20260819_0001
Create Date: 2026-08-19
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260819_0002"
down_revision: str | Sequence[str] | None = "20260819_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "seats", "showtime_id", existing_type=sa.Integer(), nullable=True
    )
    op.create_unique_constraint("uq_room_seat", "seats", ["room_id", "seat_label"])


def downgrade() -> None:
    orphan_count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM seats WHERE showtime_id IS NULL")
    ).scalar_one()
    if orphan_count:
        raise RuntimeError(
            "Cannot restore seats.showtime_id NOT NULL while physical seats exist"
        )
    op.drop_constraint("uq_room_seat", "seats", type_="unique")
    op.alter_column(
        "seats", "showtime_id", existing_type=sa.Integer(), nullable=False
    )
