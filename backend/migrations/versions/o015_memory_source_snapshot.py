"""Preserve the underlying sources of the extracted note version.

Revision ID: o015_memory_sources
Revises: n014_memory
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "o015_memory_sources"
down_revision = "n014_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("source_snapshot", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    # Only matching versions can be reconstructed. Never substitute a note's newer links.
    op.execute(
        sa.text("""
        UPDATE memories AS memory
        SET source_snapshot = COALESCE((
            SELECT jsonb_agg(nested.ref)
            FROM jsonb_array_elements(memory.source_refs) AS source(ref)
            JOIN notes AS note
              ON source.ref->>'source_type' = 'note'
             AND note.id = source.ref->>'source_id'
             AND note.owner_id = memory.owner_id
             AND note.version = (source.ref->>'source_version')::integer
            CROSS JOIN LATERAL jsonb_array_elements(note.source_refs) AS nested(ref)
        ), '[]'::jsonb)
    """)
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM memories)")):
        raise RuntimeError("Memory source snapshots exist; destructive downgrade refused")
    op.drop_column("memories", "source_snapshot")
