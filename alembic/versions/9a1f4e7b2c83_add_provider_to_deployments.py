"""add provider column to deployments

Revision ID: 9a1f4e7b2c83
Revises: d4e5f6a7b8c9
Create Date: 2026-06-06 00:00:00.000000

Menambahkan kolom `provider` pada tabel deployments untuk mendukung
multi-provider (Proxmox, AWS, dst). Default 'proxmox' agar data lama konsisten.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '9a1f4e7b2c83'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'deployments',
        sa.Column('provider', sa.String(length=20), nullable=False, server_default='proxmox'),
    )
    op.create_index('ix_deployments_provider', 'deployments', ['provider'])


def downgrade() -> None:
    op.drop_index('ix_deployments_provider', table_name='deployments')
    op.drop_column('deployments', 'provider')
