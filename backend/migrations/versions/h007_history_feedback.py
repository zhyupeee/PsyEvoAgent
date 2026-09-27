"""STEP07 feedback and immutable run revision edges; preserve existing history."""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "h007_history_feedback"
down_revision = "d642b94fcbb5"
branch_labels = None
depends_on = None


def personal() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("retention_policy_id", sa.String(80), nullable=False),
        sa.Column("source_refs", postgresql.JSONB(), nullable=False),
        sa.Column("consent_refs", postgresql.JSONB(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "feedback",
        *personal(),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("helpfulness", sa.String(20), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("notice_version", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(["run_id", "owner_id"], ["runs.id", "runs.owner_id"]),
        sa.CheckConstraint("helpfulness IN ('helpful','neutral','unhelpful','not_rated')"),
        sa.CheckConstraint("category IN ('general','misunderstood','listen_only','inappropriate')"),
    )
    op.create_index("ix_feedback_owner_id", "feedback", ["owner_id"])
    op.create_table(
        "run_branches",
        *personal(),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("parent_run_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(["run_id", "owner_id"], ["runs.id", "runs.owner_id"]),
        sa.ForeignKeyConstraint(["parent_run_id", "owner_id"], ["runs.id", "runs.owner_id"]),
        sa.UniqueConstraint("run_id"),
        sa.UniqueConstraint("parent_run_id"),
        sa.CheckConstraint("kind IN ('revision','regenerate')"),
    )
    op.create_index("ix_run_branches_owner_id", "run_branches", ["owner_id"])


def downgrade() -> None:
    for table in ("feedback", "run_branches"):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("Cannot discard STEP07 history")
    op.drop_table("run_branches")
    op.drop_table("feedback")
