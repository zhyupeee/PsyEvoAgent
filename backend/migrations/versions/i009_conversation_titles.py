"""Conversation title provenance and a content-free, single-attempt task."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "i009_conversation_titles"
down_revision = "h007_history_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("title_source", sa.String(12), nullable=False, server_default="default"),
    )
    op.add_column(
        "conversations",
        sa.Column("title_revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "title_generation_status", sa.String(20), nullable=False, server_default="not_requested"
        ),
    )
    op.execute("UPDATE conversations SET title_source = 'manual' WHERE title <> '新的对话'")
    op.create_table(
        "title_tasks",
        sa.Column("session_id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("title_revision", sa.Integer(), nullable=False),
        sa.Column("message_versions", postgresql.JSONB(), nullable=False),
        sa.Column("profile", postgresql.JSONB(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id", "owner_id"], ["conversations.id", "conversations.owner_id"]
        ),
        sa.ForeignKeyConstraint(["run_id", "owner_id"], ["runs.id", "runs.owner_id"]),
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM title_tasks) OR EXISTS "
            "(SELECT 1 FROM conversations WHERE title_revision > 1 OR title_source = 'auto')"
        )
    ):
        raise RuntimeError("Cannot discard automatic title history")
    op.drop_table("title_tasks")
    for column in ("title_generation_status", "title_revision", "title_source"):
        op.drop_column("conversations", column)
