"""smart-id: медзаписи, история изменений и доступы по ссылке

Revision ID: 0006_smart_id
Revises: 0005_idempotency
"""
import sqlalchemy as sa

from alembic import op

revision = "0006_smart_id"
down_revision = "0005_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "medical_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="visit"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("clinic_name", sa.String(200)),
        sa.Column("author_type", sa.String(16), nullable=False, server_default="owner"),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("external_id", sa.String(128)),
        sa.Column("description", sa.Text()),
        sa.Column("diagnosis", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_medical_records_pet_id", "medical_records", ["pet_id"])
    op.create_index("ix_medical_records_occurred_at", "medical_records", ["occurred_at"])

    op.create_table(
        "record_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "record_id",
            sa.Integer(),
            sa.ForeignKey("medical_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("changed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_record_revisions_record_id", "record_revisions", ["record_id"])

    op.create_table(
        "access_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_access_grants_pet_id", "access_grants", ["pet_id"])
    op.create_index("ix_access_grants_token_hash", "access_grants", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_access_grants_token_hash", table_name="access_grants")
    op.drop_index("ix_access_grants_pet_id", table_name="access_grants")
    op.drop_table("access_grants")
    op.drop_index("ix_record_revisions_record_id", table_name="record_revisions")
    op.drop_table("record_revisions")
    op.drop_index("ix_medical_records_occurred_at", table_name="medical_records")
    op.drop_index("ix_medical_records_pet_id", table_name="medical_records")
    op.drop_table("medical_records")
