"""owner password: users.password_hash, failed_login_attempts, locked_until

Revision ID: 0004_owner_password
Revises: 0003_auth_foundation
"""
import sqlalchemy as sa

from alembic import op

revision = "0004_owner_password"
down_revision = "0003_auth_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "password_hash")
