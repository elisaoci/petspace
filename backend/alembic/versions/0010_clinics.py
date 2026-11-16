"""clinics, clinic_documents, clinic_staff: основа кабинета клиники

Revision ID: 0010_clinics
Revises: 0009_analytics
"""
import sqlalchemy as sa

from alembic import op

revision = "0010_clinics"
down_revision = "0009_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("inn", sa.String(12), nullable=False),
        sa.Column("address", sa.String(300), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("status_reason", sa.String(1000)),
        sa.Column("moderated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("moderated_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("inn", "address", name="uq_clinics_inn_address"),
    )
    op.create_index("ix_clinics_inn", "clinics", ["inn"])
    op.create_index("ix_clinics_status", "clinics", ["status"])

    op.create_table(
        "clinic_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinic_id", sa.Integer(), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clinic_documents_clinic_id", "clinic_documents", ["clinic_id"])

    op.create_table(
        "clinic_staff",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinic_id", sa.Integer(), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clinic_staff_clinic_id", "clinic_staff", ["clinic_id"])
    op.create_index("ix_clinic_staff_user_id", "clinic_staff", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_clinic_staff_user_id", table_name="clinic_staff")
    op.drop_index("ix_clinic_staff_clinic_id", table_name="clinic_staff")
    op.drop_table("clinic_staff")
    op.drop_index("ix_clinic_documents_clinic_id", table_name="clinic_documents")
    op.drop_table("clinic_documents")
    op.drop_index("ix_clinics_status", table_name="clinics")
    op.drop_index("ix_clinics_inn", table_name="clinics")
    op.drop_table("clinics")
