"""add compose_content to levels

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-05

Simpan isi docker-compose.yml di Level saat prepare, supaya deploy tidak perlu
clone repo dari GitHub lagi (cukup inject content ke VM via Ansible copy).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('levels', sa.Column('compose_content', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('levels', 'compose_content')
