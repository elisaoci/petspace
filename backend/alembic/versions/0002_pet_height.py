"""add pet height

Revision ID: 0002_pet_height
Revises: 0001_petspace_domain
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_pet_height"
down_revision = "0001_petspace_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pets", sa.Column("height_cm", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("pets", "height_cm")
