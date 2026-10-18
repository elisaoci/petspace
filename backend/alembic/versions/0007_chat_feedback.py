"""chat feedback: оценка ответов ИИ

Revision ID: 0007_chat_feedback
Revises: 0006_smart_id
"""
import sqlalchemy as sa

from alembic import op

revision = "0007_chat_feedback"
down_revision = "0006_smart_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("feedback", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "feedback")
