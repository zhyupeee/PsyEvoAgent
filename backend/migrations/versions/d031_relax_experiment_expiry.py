"""Make experiment business expiry optional without deleting existing records."""

import sqlalchemy as sa
from alembic import op

revision = "d031_experiment_expiry"
down_revision = "c1756470d092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("consent_records", "runs", "context_grants"):
        op.alter_column(
            table, "expires_at", existing_type=sa.DateTime(timezone=True), nullable=True
        )


def downgrade() -> None:
    # Never invent expiry dates for records created under the no-expiry contract.
    connection = op.get_bind()
    for table in ("consent_records", "runs", "context_grants"):
        if connection.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE expires_at IS NULL")):
            raise RuntimeError("Cannot restore mandatory expiry for no-expiry experiment records")
    for table in ("consent_records", "runs", "context_grants"):
        op.alter_column(
            table, "expires_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
