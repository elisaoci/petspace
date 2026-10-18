"""stage 2 completion: убрать оценку ИИ, добавить поля профиля и записи в клинику

Revision ID: 0008_stage2_completion
Revises: 0007_chat_feedback
"""
import sqlalchemy as sa

from alembic import op

revision = "0008_stage2_completion"
down_revision = "0007_chat_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Оценку ответов ИИ убрали: сигнал оказался не нужен на этом этапе.
    op.drop_column("chat_messages", "feedback")

    # Поля профиля из ТЗ: аллергии и хронические болезни (шифруются приложением).
    op.add_column("pets", sa.Column("allergies", sa.Text()))
    op.add_column("pets", sa.Column("chronic_conditions", sa.Text()))

    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clinic_name", sa.String(200), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_appointments_pet_id", "appointments", ["pet_id"])
    op.create_index("ix_appointments_slot_start", "appointments", ["slot_start"])


def downgrade() -> None:
    op.drop_index("ix_appointments_slot_start", table_name="appointments")
    op.drop_index("ix_appointments_pet_id", table_name="appointments")
    op.drop_table("appointments")
    op.drop_column("pets", "chronic_conditions")
    op.drop_column("pets", "allergies")
    op.add_column("chat_messages", sa.Column("feedback", sa.String(16), nullable=True))
