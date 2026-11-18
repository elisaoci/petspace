"""приёмы в клинике, вложения к медзаписям, связь записи с приёмом

Revision ID: 0012_encounters
Revises: 0011_patient_access
"""
import sqlalchemy as sa

from alembic import op

revision = "0012_encounters"
down_revision = "0011_patient_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "encounters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinic_id", sa.Integer(), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_encounters_clinic_id", "encounters", ["clinic_id"])
    op.create_index("ix_encounters_pet_id", "encounters", ["pet_id"])
    op.create_index("ix_encounters_status", "encounters", ["status"])
    op.create_index(
        "uq_encounters_one_open_per_pet",
        "encounters",
        ["clinic_id", "pet_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
    )

    op.add_column("medical_records", sa.Column("encounter_id", sa.Integer()))
    op.create_foreign_key(
        "medical_records_encounter_id_fkey",
        "medical_records",
        "encounters",
        ["encounter_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_medical_records_encounter_id", "medical_records", ["encounter_id"])

    op.create_table(
        "record_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("record_id", sa.Integer(), sa.ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_record_attachments_record_id", "record_attachments", ["record_id"])


def downgrade() -> None:
    op.drop_index("ix_record_attachments_record_id", table_name="record_attachments")
    op.drop_table("record_attachments")

    op.drop_index("ix_medical_records_encounter_id", table_name="medical_records")
    op.drop_constraint("medical_records_encounter_id_fkey", "medical_records", type_="foreignkey")
    op.drop_column("medical_records", "encounter_id")

    op.drop_index("uq_encounters_one_open_per_pet", table_name="encounters")
    op.drop_index("ix_encounters_status", table_name="encounters")
    op.drop_index("ix_encounters_pet_id", table_name="encounters")
    op.drop_index("ix_encounters_clinic_id", table_name="encounters")
    op.drop_table("encounters")
