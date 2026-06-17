"""add unique active deployment constraint

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-04 00:00:00.000000

Mencegah race condition: satu tim hanya boleh punya satu deployment aktif per level.
Constraint di level DB (bukan hanya application level) agar concurrent request tidak bypass.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Partial unique index: (level_id, team) WHERE is_active = 1
    # SQLite mendukung partial index via WHERE clause
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_challenges_active_deployment
        ON challenges (level_id, team)
        WHERE is_active = 1
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_challenges_active_deployment")
