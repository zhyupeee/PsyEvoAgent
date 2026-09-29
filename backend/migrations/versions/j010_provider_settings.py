"""Per-account provider selection and encrypted key metadata."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "j010_provider_settings"
down_revision = "i009_conversation_titles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("retention_policy_id", sa.String(80), nullable=False),
        sa.Column("source_refs", JSONB(), nullable=False),
        sa.Column("consent_refs", JSONB(), nullable=False),
        sa.Column("mode", sa.String(12), nullable=False, server_default="official"),
        sa.Column("base_url", sa.String(500)),
        sa.Column("model", sa.String(200)),
        sa.Column("encrypted_api_key", sa.Text()),
        sa.Column("deadline_seconds", sa.Float(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.UniqueConstraint("owner_id"),
        sa.CheckConstraint("mode IN ('official','custom')"),
        sa.CheckConstraint("version > 0"),
    )
    op.create_index("ix_provider_settings_owner_id", "provider_settings", ["owner_id"])
    op.create_table(
        "provider_bindings",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("custom", sa.Boolean(), nullable=False),
        sa.Column("encrypted_config", sa.Text()),
    )
    op.create_index("ix_provider_bindings_owner_id", "provider_bindings", ["owner_id"])


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM provider_settings) OR EXISTS (SELECT 1 FROM provider_bindings)"
        )
    ):
        raise RuntimeError("Provider configuration exists; destructive downgrade refused")
    op.drop_table("provider_bindings")
    op.drop_table("provider_settings")
