"""Add indexes used by movie and showtime discovery queries.

Revision ID: 20260820_0005
Revises: 20260820_0004
Create Date: 2026-08-20
"""

from typing import Sequence

from alembic import op


revision: str = "20260820_0005"
down_revision: str | Sequence[str] | None = "20260820_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_showtimes_movie_id", "showtimes", ["movie_id"])
    op.create_index("ix_showtimes_start_time", "showtimes", ["start_time"])


def downgrade() -> None:
    op.drop_index("ix_showtimes_start_time", table_name="showtimes")
    op.drop_index("ix_showtimes_movie_id", table_name="showtimes")
