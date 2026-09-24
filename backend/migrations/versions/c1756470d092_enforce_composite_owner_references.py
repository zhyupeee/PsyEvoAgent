"""Enforce composite owner references

Revision ID: c1756470d092
Revises: 7af8981db341
Create Date: 2026-09-21 16:46:23.879707

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1756470d092"
down_revision: str | Sequence[str] | None = "7af8981db341"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint("uq_consent_owner", "consent_records", ["id", "owner_id"])
    op.create_unique_constraint("uq_run_owner", "runs", ["id", "owner_id"])
    op.create_foreign_key(
        "fk_grant_run_owner", "context_grants", "runs", ["run_id", "owner_id"], ["id", "owner_id"]
    )
    op.create_foreign_key(
        "fk_grant_source_owner",
        "context_grants",
        "conversations",
        ["source_id", "owner_id"],
        ["id", "owner_id"],
    )
    op.create_foreign_key(
        "fk_grant_consent_owner",
        "context_grants",
        "consent_records",
        ["consent_id", "owner_id"],
        ["id", "owner_id"],
    )
    op.create_foreign_key(
        "fk_deletion_target_owner",
        "deletion_jobs",
        "conversations",
        ["target", "owner_id"],
        ["id", "owner_id"],
    )
    op.create_foreign_key(
        "fk_run_session_owner",
        "runs",
        "conversations",
        ["session_id", "owner_id"],
        ["id", "owner_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_run_session_owner", "runs", type_="foreignkey")
    op.drop_constraint("fk_deletion_target_owner", "deletion_jobs", type_="foreignkey")
    op.drop_constraint("fk_grant_consent_owner", "context_grants", type_="foreignkey")
    op.drop_constraint("fk_grant_source_owner", "context_grants", type_="foreignkey")
    op.drop_constraint("fk_grant_run_owner", "context_grants", type_="foreignkey")
    op.drop_constraint("uq_consent_owner", "consent_records", type_="unique")
    op.drop_constraint("uq_run_owner", "runs", type_="unique")
