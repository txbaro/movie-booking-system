"""Add semantic movie embeddings and recommendation event context.

Revision ID: 20260820_0009
Revises: 20260820_0008
Create Date: 2026-08-20
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260820_0009"
down_revision: str | Sequence[str] | None = "20260820_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "user_events",
        "search_query",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.add_column("user_events", sa.Column("context_id", sa.String(36)))
    op.add_column("user_events", sa.Column("event_data", sa.JSON()))
    op.create_index("ix_user_events_context_id", "user_events", ["context_id"])
    op.drop_constraint(
        "ck_user_events_event_type", "user_events", type_="check"
    )
    op.create_check_constraint(
        "ck_user_events_event_type",
        "user_events",
        "event_type IN ('movie_viewed', 'movie_searched', "
        "'showtimes_viewed', 'external_booking_clicked', "
        "'preference_prompt_submitted', 'recommendation_clicked')",
    )

    op.create_table(
        "movie_embeddings",
        sa.Column(
            "movie_id",
            sa.Integer(),
            sa.ForeignKey("movies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("movie_embeddings")
    op.drop_constraint(
        "ck_user_events_event_type", "user_events", type_="check"
    )
    op.create_check_constraint(
        "ck_user_events_event_type",
        "user_events",
        "event_type IN ('movie_viewed', 'movie_searched', "
        "'showtimes_viewed', 'external_booking_clicked')",
    )
    op.drop_index("ix_user_events_context_id", table_name="user_events")
    op.drop_column("user_events", "event_data")
    op.drop_column("user_events", "context_id")
    op.alter_column(
        "user_events",
        "search_query",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
