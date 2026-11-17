"""доступ клиники к пациенту: запросы, коды, привязка доступов к клинике

Revision ID: 0011_patient_access
Revises: 0010_clinics
"""
import sqlalchemy as sa

from alembic import op

revision = "0011_patient_access"
down_revision = "0010_clinics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Доступ клиники — тот же access_grants, но с clinic_id и без публичного токена.
    op.add_column("access_grants", sa.Column("clinic_id", sa.Integer()))
    op.create_foreign_key(
        "access_grants_clinic_id_fkey", "access_grants", "clinics", ["clinic_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_access_grants_clinic_id", "access_grants", ["clinic_id"])
    op.alter_column("access_grants", "token_hash", existing_type=sa.String(128), nullable=True)

    op.create_table(
        "access_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinic_id", sa.Integer(), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id", ondelete="CASCADE")),
        sa.Column("pet_name_query", sa.String(120), nullable=False),
        sa.Column("owner_phone_query", sa.String(32), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("ttl_days", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("grant_id", sa.Integer(), sa.ForeignKey("access_grants.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_access_requests_clinic_id", "access_requests", ["clinic_id"])
    op.create_index("ix_access_requests_pet_id", "access_requests", ["pet_id"])
    op.create_index("ix_access_requests_status", "access_requests", ["status"])

    op.create_table(
        "access_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("ttl_days", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("used_by_clinic_id", sa.Integer(), sa.ForeignKey("clinics.id", ondelete="SET NULL")),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_access_codes_pet_id", "access_codes", ["pet_id"])
    op.create_index("ix_access_codes_code_hash", "access_codes", ["code_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_access_codes_code_hash", table_name="access_codes")
    op.drop_index("ix_access_codes_pet_id", table_name="access_codes")
    op.drop_table("access_codes")

    op.drop_index("ix_access_requests_status", table_name="access_requests")
    op.drop_index("ix_access_requests_pet_id", table_name="access_requests")
    op.drop_index("ix_access_requests_clinic_id", table_name="access_requests")
    op.drop_table("access_requests")

    # Доступы клиник не имеют токена и не переживут возврат NOT NULL.
    op.execute("DELETE FROM access_grants WHERE token_hash IS NULL")
    op.alter_column("access_grants", "token_hash", existing_type=sa.String(128), nullable=False)
    op.drop_index("ix_access_grants_clinic_id", table_name="access_grants")
    op.drop_constraint("access_grants_clinic_id_fkey", "access_grants", type_="foreignkey")
    op.drop_column("access_grants", "clinic_id")
