"""Make historical consent references optional; never synthesize user decisions."""

import sqlalchemy as sa
from alembic import op

revision = "e032_experiment_defaults"
down_revision = "d031_experiment_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("context_grants", "consent_id", existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM context_grants WHERE consent_id IS NULL")
    ):
        raise RuntimeError("Cannot invent historical consent for experiment source links")
    op.alter_column("context_grants", "consent_id", existing_type=sa.String(36), nullable=False)
