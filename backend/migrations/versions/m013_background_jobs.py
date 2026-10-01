"""S2-STEP03 durable jobs; no extraction or memory tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "m013_background_jobs"
down_revision = "l012_records"
branch_labels = None
depends_on = None


def record() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    ]


def upgrade() -> None:
    op.create_table(
        "job_budgets",
        *record(),
        sa.Column("limits", JSONB, nullable=False),
        sa.Column("calls", JSONB, nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "owner_id"),
    )
    op.create_table(
        "background_jobs",
        *record(),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("retention_policy_id", sa.String(80), nullable=False),
        sa.Column("source_refs", JSONB, nullable=False),
        sa.Column("consent_refs", JSONB, nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("generation", sa.Integer, nullable=False),
        sa.Column("experiment_config_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("max_attempts", sa.Integer, nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("budget_ref", sa.String(36), nullable=False),
        sa.Column("lease_owner", sa.String(36)),
        sa.Column("lease_token", sa.Integer, nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(60)),
        sa.Column("result_ref", sa.String(36)),
        sa.Column("lease_losses", sa.Integer, nullable=False),
        sa.UniqueConstraint("id", "owner_id"),
        sa.UniqueConstraint("owner_id", "kind", "source_key", "generation"),
        sa.ForeignKeyConstraint(
            ["budget_ref", "owner_id"], ["job_budgets.id", "job_budgets.owner_id"]
        ),
        sa.CheckConstraint("purpose = 'candidate_extraction'"),
        sa.CheckConstraint(
            "status IN ('queued','running','retry_wait','succeeded','failed',"
            "'cancelled','invalidated')"
        ),
        sa.CheckConstraint("version > 0 AND generation > 0 AND lease_token >= 0"),
        sa.CheckConstraint(
            "attempt >= 0 AND max_attempts BETWEEN 1 AND 5 AND attempt <= max_attempts"
        ),
        sa.CheckConstraint(
            "(status = 'running' AND lease_owner IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(status <> 'running' AND lease_owner IS NULL AND lease_until IS NULL)"
        ),
    )
    for table in ("job_budgets", "background_jobs"):
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])
    op.create_index(
        "ix_background_jobs_recovery", "background_jobs", ["status", "available_at", "lease_until"]
    )
    for constraint in sa.inspect(op.get_bind()).get_check_constraints("context_grants"):
        if "purpose" in constraint["sqltext"]:
            op.drop_constraint(constraint["name"], "context_grants", type_="check")
    op.alter_column("context_grants", "run_id", nullable=True)
    op.add_column("context_grants", sa.Column("job_id", sa.String(36)))
    op.create_index("ix_context_grants_job_id", "context_grants", ["job_id"])
    op.create_foreign_key(
        "fk_grant_job_owner",
        "context_grants",
        "background_jobs",
        ["job_id", "owner_id"],
        ["id", "owner_id"],
    )
    op.create_check_constraint(
        "ck_grant_execution_scope",
        "context_grants",
        "(purpose = 'current_run' AND run_id IS NOT NULL AND job_id IS NULL) OR "
        "(purpose = 'candidate_extraction' AND run_id IS NULL AND job_id IS NOT NULL)",
    )


def downgrade() -> None:
    for table in ("background_jobs", "job_budgets"):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("Durable job/budget receipts exist; destructive downgrade refused")
    op.drop_constraint("ck_grant_execution_scope", "context_grants", type_="check")
    op.drop_constraint("fk_grant_job_owner", "context_grants", type_="foreignkey")
    op.drop_index("ix_context_grants_job_id", "context_grants")
    op.drop_column("context_grants", "job_id")
    op.alter_column("context_grants", "run_id", nullable=False)
    op.create_check_constraint("ck_grant_current_run", "context_grants", "purpose = 'current_run'")
    op.drop_table("background_jobs")
    op.drop_table("job_budgets")
