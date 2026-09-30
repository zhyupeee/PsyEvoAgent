"""S2-STEP02 records and typed references; preserve all stage-1 rows."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "l012_records"
down_revision = "k011_provider_tests"
branch_labels = None
depends_on = None


def personal() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("retention_policy_id", sa.String(80), nullable=False),
        sa.Column("source_refs", JSONB, nullable=False),
        sa.Column("consent_refs", JSONB, nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "notes",
        *personal(),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("annotation", sa.Text, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("timezone", sa.String(80)),
        sa.Column("tags", JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.UniqueConstraint("id", "owner_id"),
        sa.CheckConstraint("version > 0"),
        sa.CheckConstraint("kind IN ('free','linked_excerpt')"),
        sa.CheckConstraint("status IN ('draft','saved','needs_review','deleted')"),
        sa.CheckConstraint("kind <> 'linked_excerpt' OR body IS NULL"),
    )
    op.create_table(
        "sleep_records",
        *personal(),
        sa.Column("entry_date", sa.Date),
        sa.Column("bed_at", sa.DateTime(timezone=True)),
        sa.Column("wake_at", sa.DateTime(timezone=True)),
        sa.Column("timezone", sa.String(80)),
        sa.Column("interruptions", sa.Integer),
        sa.Column("feeling", sa.String(200), nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.UniqueConstraint("id", "owner_id"),
        sa.CheckConstraint("version > 0"),
        sa.CheckConstraint("deleted_at IS NOT NULL OR entry_date IS NOT NULL"),
        sa.CheckConstraint("interruptions IS NULL OR interruptions >= 0"),
        sa.CheckConstraint("bed_at IS NULL OR wake_at IS NULL OR wake_at > bed_at"),
    )
    op.create_table(
        "support_cards",
        *personal(),
        sa.Column("helpful_methods", sa.Text, nullable=False),
        sa.Column("self_reminders", sa.Text, nullable=False),
        sa.Column("contact_notes", sa.Text, nullable=False),
        sa.Column("resource_refs", JSONB, nullable=False),
        sa.Column("previous_content", JSONB),
        sa.UniqueConstraint("id", "owner_id"),
        sa.UniqueConstraint("owner_id"),
        sa.CheckConstraint("version > 0"),
    )
    for table in ("notes", "sleep_records", "support_cards"):
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])
    op.create_unique_constraint("uq_message_owner", "messages", ["id", "owner_id"])
    op.create_table(
        "note_sources",
        sa.Column("note_id", sa.String(36), primary_key=True),
        sa.Column("message_id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("message_version", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(["note_id", "owner_id"], ["notes.id", "notes.owner_id"]),
        sa.ForeignKeyConstraint(["message_id", "owner_id"], ["messages.id", "messages.owner_id"]),
        sa.CheckConstraint("message_version > 0"),
    )
    op.add_column(
        "deletion_jobs",
        sa.Column("target_type", sa.String(30), nullable=False, server_default="conversation"),
    )
    for table, ref, kind, suffix in (
        ("context_grants", "source_id", "source_type", "source"),
        ("deletion_jobs", "target", "target_type", "target"),
    ):
        # Remove only the old conversation target FKs, including the composite FK.
        for fk in sa.inspect(op.get_bind()).get_foreign_keys(table):
            if ref in fk["constrained_columns"]:
                op.drop_constraint(fk["name"], table, type_="foreignkey")
        op.create_check_constraint(
            f"ck_{table}_typed",
            table,
            f"{kind} IN ('conversation','note','sleep_record','support_card')",
        )
        for value, prefix, target in (
            ("conversation", "conversation", "conversations"),
            ("note", "note", "notes"),
            ("sleep_record", "sleep", "sleep_records"),
            ("support_card", "card", "support_cards"),
        ):
            column = f"{prefix}_{suffix}_id"
            op.add_column(
                table,
                sa.Column(
                    column,
                    sa.String(36),
                    sa.Computed(f"CASE WHEN {kind} = '{value}' THEN {ref} END", persisted=True),
                ),
            )
            op.create_foreign_key(
                f"fk_{table}_{prefix}_owner",
                table,
                target,
                [column, "owner_id"],
                ["id", "owner_id"],
            )


def downgrade() -> None:
    for table in ("notes", "sleep_records", "support_cards"):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("Record/source receipts exist; destructive downgrade refused")
    for table, ref, suffix in (
        ("context_grants", "source_id", "source"),
        ("deletion_jobs", "target", "target"),
    ):
        for prefix in ("conversation", "note", "sleep", "card"):
            op.drop_constraint(f"fk_{table}_{prefix}_owner", table, type_="foreignkey")
            op.drop_column(table, f"{prefix}_{suffix}_id")
        op.drop_constraint(f"ck_{table}_typed", table, type_="check")
        op.create_foreign_key(f"{table}_{ref}_fkey", table, "conversations", [ref], ["id"])
        name = "fk_grant_source_owner" if table == "context_grants" else "fk_deletion_target_owner"
        op.create_foreign_key(name, table, "conversations", [ref, "owner_id"], ["id", "owner_id"])
    op.drop_column("deletion_jobs", "target_type")
    op.drop_table("note_sources")
    op.drop_constraint("uq_message_owner", "messages", type_="unique")
    for table in ("support_cards", "sleep_records", "notes"):
        op.drop_table(table)
