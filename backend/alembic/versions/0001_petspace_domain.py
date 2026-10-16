"""create petspace domain tables

Revision ID: 0001_petspace_domain
"""
import sqlalchemy as sa

from alembic import op

revision = "0001_petspace_domain"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("pets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("species", sa.String(80), nullable=False, server_default="dog"),
        sa.Column("breed", sa.String(120)), sa.Column("birth_date", sa.Date()),
        sa.Column("sex", sa.String(20)), sa.Column("weight_kg", sa.Float()),
        sa.Column("photo_url", sa.String(500)), sa.Column("owner_notes", sa.Text()),
        sa.Column("medical_secret_token", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_pets_medical_secret_token", "pets", ["medical_secret_token"])
    op.create_table("calendar_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("event_type", sa.String(50), nullable=False, server_default="other"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True)), sa.Column("status", sa.String(20), nullable=False, server_default="planned"))
    op.create_index("ix_calendar_events_pet_id", "calendar_events", ["pet_id"])
    op.create_table("chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id", ondelete="CASCADE")),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("role", sa.String(20), nullable=False), sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_chat_messages_pet_id", "chat_messages", ["pet_id"])
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])
    op.create_table("subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("starts_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True)))
    op.create_index("ix_subscriptions_owner_id", "subscriptions", ["owner_id"])

def downgrade() -> None:
    op.drop_table("subscriptions"); op.drop_table("chat_messages")
    op.drop_table("calendar_events"); op.drop_index("ix_pets_medical_secret_token", table_name="pets"); op.drop_table("pets")
