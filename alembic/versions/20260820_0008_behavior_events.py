"""Add behavioral events for personalized recommendations.

Revision ID: 20260820_0008
Revises: 20260820_0007
Create Date: 2026-08-20
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260820_0008"
down_revision: str | Sequence[str] | None = "20260820_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "movie_id",
            sa.Integer(),
            sa.ForeignKey("movies.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "cinema_id",
            sa.Integer(),
            sa.ForeignKey("cinemas.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "showtime_id",
            sa.Integer(),
            sa.ForeignKey("showtimes.id", ondelete="SET NULL"),
        ),
        sa.Column("source", sa.String(50)),
        sa.Column("search_query", sa.String(255)),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "event_type IN ('movie_viewed', 'movie_searched', "
            "'showtimes_viewed', 'external_booking_clicked')",
            name="ck_user_events_event_type",
        ),
    )
    op.create_index("ix_user_events_user_id", "user_events", ["user_id"])
    op.create_index("ix_user_events_event_type", "user_events", ["event_type"])
    op.create_index("ix_user_events_movie_id", "user_events", ["movie_id"])
    op.create_index(
        "ix_user_events_user_occurred_at",
        "user_events",
        ["user_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_events_user_occurred_at", table_name="user_events")
    op.drop_index("ix_user_events_movie_id", table_name="user_events")
    op.drop_index("ix_user_events_event_type", table_name="user_events")
    op.drop_index("ix_user_events_user_id", table_name="user_events")
    op.drop_table("user_events")
