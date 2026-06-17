"""add scoring params to levels

Revision ID: a1b2c3d4e5f6
Revises: d5d37266c4ec
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd5d37266c4ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('levels', sa.Column('initial_points', sa.Integer(), nullable=False, server_default='1000'))
    op.add_column('levels', sa.Column('minimum_points', sa.Integer(), nullable=False, server_default='100'))
    op.add_column('levels', sa.Column('decay', sa.Integer(), nullable=False, server_default='25'))


def downgrade() -> None:
    op.drop_column('levels', 'decay')
    op.drop_column('levels', 'minimum_points')
    op.drop_column('levels', 'initial_points')
