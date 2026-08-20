"""Align the legacy users email constraint with fresh databases.

Revision ID: 20260820_0007
Revises: 20260820_0006
Create Date: 2026-08-20
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260820_0007"
down_revision: str | Sequence[str] | None = "20260820_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    constraints = {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_unique_constraints("users")
    }
    if "uq_users_email" not in constraints:
        op.create_unique_constraint("uq_users_email", "users", ["email"])


def downgrade() -> None:
    # Revision 0001 already defines this invariant for newly-created databases.
    # Keep it when crossing this compatibility-only migration on legacy databases.
    pass
