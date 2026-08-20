"""Add ingestion identities, sync timestamps, and cinema coordinates.

Revision ID: 20260819_0003
Revises: 20260819_0002
Create Date: 2026-08-19
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260819_0003"
down_revision: str | Sequence[str] | None = "20260819_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INGESTION_TABLES = ("cinemas", "cinema_rooms", "movies", "showtimes")


def upgrade() -> None:
    for table in INGESTION_TABLES:
        op.add_column(table, sa.Column("source", sa.String(50), nullable=True))
        op.add_column(table, sa.Column("external_id", sa.String(255), nullable=True))
        op.add_column(
            table,
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        )

    op.add_column("cinemas", sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("cinemas", sa.Column("longitude", sa.Numeric(9, 6), nullable=True))
    op.create_check_constraint(
        "ck_cinemas_latitude",
        "cinemas",
        "latitude IS NULL OR latitude BETWEEN -90 AND 90",
    )
    op.create_check_constraint(
        "ck_cinemas_longitude",
        "cinemas",
        "longitude IS NULL OR longitude BETWEEN -180 AND 180",
    )

    for table in INGESTION_TABLES:
        op.create_index(
            f"uq_{table}_source_external_id",
            table,
            ["source", "external_id"],
            unique=True,
            postgresql_where=sa.text("external_id IS NOT NULL"),
        )


def downgrade() -> None:
    for table in reversed(INGESTION_TABLES):
        op.drop_index(f"uq_{table}_source_external_id", table_name=table)

    op.drop_constraint("ck_cinemas_longitude", "cinemas", type_="check")
    op.drop_constraint("ck_cinemas_latitude", "cinemas", type_="check")
    op.drop_column("cinemas", "longitude")
    op.drop_column("cinemas", "latitude")

    for table in reversed(INGESTION_TABLES):
        op.drop_column(table, "last_synced_at")
        op.drop_column(table, "external_id")
        op.drop_column(table, "source")
