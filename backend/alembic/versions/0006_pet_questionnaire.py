"""expand pet questionnaire

Revision ID: 0006_pet_questionnaire
Revises: 0005_idempotency
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_pet_questionnaire"
down_revision = "0005_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pets", sa.Column("approximate_age_years", sa.Integer()))
    op.add_column("pets", sa.Column("color", sa.String(120)))
    op.add_column("pets", sa.Column("distinguishing_marks", sa.Text()))
    op.add_column("pets", sa.Column("sterilization_status", sa.String(20)))
    op.add_column("pets", sa.Column("sterilization_date", sa.Date()))
    op.add_column("pets", sa.Column("microchip_number", sa.String(80)))
    op.add_column("pets", sa.Column("allergies", sa.Text()))
    op.add_column("pets", sa.Column("chronic_conditions", sa.Text()))
    op.add_column("pets", sa.Column("rabies_vaccine_date", sa.Date()))
    op.add_column("pets", sa.Column("complex_vaccine_date", sa.Date()))
    op.add_column("pets", sa.Column("temperament", sa.JSON()))
    op.add_column("pets", sa.Column("aggressive", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("pets", sa.Column("feeding_notes", sa.Text()))
    op.add_column("pets", sa.Column("insurance_company", sa.String(160)))
    op.add_column("pets", sa.Column("insurance_policy_number", sa.String(120)))
    op.add_column("pets", sa.Column("vet_passport_url", sa.String(500)))


def downgrade() -> None:
    for column in (
        "vet_passport_url",
        "insurance_policy_number",
        "insurance_company",
        "feeding_notes",
        "aggressive",
        "temperament",
        "complex_vaccine_date",
        "rabies_vaccine_date",
        "chronic_conditions",
        "allergies",
        "microchip_number",
        "sterilization_date",
        "sterilization_status",
        "distinguishing_marks",
        "color",
        "approximate_age_years",
    ):
        op.drop_column("pets", column)
