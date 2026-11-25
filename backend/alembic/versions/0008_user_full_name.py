"""Add a display name to owner profiles.

Revision ID: 0008_user_full_name
Revises: 0007_pet_name_cases
"""
import sqlalchemy as sa

from alembic import op

revision = "0008_user_full_name"
down_revision = "0007_pet_name_cases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "full_name")
