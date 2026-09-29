"""Durable, owner-scoped receipts for explicit synthetic provider tests."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "k011_provider_tests"
down_revision = "j010_provider_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_tests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "identity_id", sa.String(36), sa.ForeignKey("identity_sessions.id"), nullable=False
        ),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("custom", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(80)),
        sa.Column("receipt", JSONB(), nullable=False),
        sa.UniqueConstraint("owner_id", "request_key"),
        sa.CheckConstraint("status IN ('running','completed','failed','cancelled','interrupted')"),
    )
    op.create_index("ix_provider_tests_owner_id", "provider_tests", ["owner_id"])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM provider_tests)")):
        raise RuntimeError("Provider test receipts exist; destructive downgrade refused")
    op.drop_table("provider_tests")
