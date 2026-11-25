"""add pet name declension cases

Revision ID: 0007_pet_name_cases
Revises: 0006_pet_questionnaire
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_pet_name_cases"
down_revision = "0006_pet_questionnaire"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pets", sa.Column("name_genitive", sa.String(120)))
    op.add_column("pets", sa.Column("name_dative", sa.String(120)))
    op.add_column("pets", sa.Column("name_accusative", sa.String(120)))
    op.add_column("pets", sa.Column("name_instrumental", sa.String(120)))
    op.add_column("pets", sa.Column("name_prepositional", sa.String(120)))


def downgrade() -> None:
    for column in (
        "name_prepositional",
        "name_instrumental",
        "name_accusative",
        "name_dative",
        "name_genitive",
    ):
        op.drop_column("pets", column)
