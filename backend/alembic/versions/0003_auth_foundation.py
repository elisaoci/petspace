"""auth foundation: users, otp_codes, refresh_tokens, consents, audit_logs, pets.owner_id

Revision ID: 0003_auth_foundation
Revises: 0002_pet_height
"""
import sqlalchemy as sa

from alembic import op

revision = "0003_auth_foundation"
down_revision = "0002_pet_height"
branch_labels = None
depends_on = None

FK_PETS_OWNER = "fk_pets_owner_id_users"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), unique=True),
        sa.Column("phone", sa.String(32), unique=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="owner"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_phone", "users", ["phone"])

    op.create_table(
        "otp_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False, server_default="login"),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("request_ip", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_otp_codes_destination", "otp_codes", ["destination"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by_id", sa.Integer()),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("ip", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])

    op.create_table(
        "consents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ip", sa.String(64)),
    )
    op.create_index("ix_consents_user_id", "consents", ["user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_type", sa.String(16), nullable=False, server_default="user"),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity", sa.String(64)),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("details", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    op.add_column("pets", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.create_index("ix_pets_owner_id", "pets", ["owner_id"])
    op.create_foreign_key(FK_PETS_OWNER, "pets", "users", ["owner_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint(FK_PETS_OWNER, "pets", type_="foreignkey")
    op.drop_index("ix_pets_owner_id", table_name="pets")
    op.drop_column("pets", "owner_id")

    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_consents_user_id", table_name="consents")
    op.drop_table("consents")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_otp_codes_destination", table_name="otp_codes")
    op.drop_table("otp_codes")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
