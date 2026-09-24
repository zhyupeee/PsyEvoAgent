"""Add email identity without rewriting historical accounts or their data."""

import sqlalchemy as sa
from alembic import op

revision = "f033_email_identity"
down_revision = "e032_experiment_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(254), nullable=True))
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_check_constraint(
        "ck_user_email_normalized", "users", "email IS NULL OR email = lower(btrim(email))"
    )
    op.alter_column("users", "username", existing_type=sa.String(80), nullable=True)
    op.create_table(
        "email_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "purpose IN ('registration', 'password_reset')", name="ck_email_code_purpose"
        ),
        sa.CheckConstraint("attempts >= 0 AND attempts <= 5", name="ck_email_code_attempts"),
    )
    op.create_index("ix_email_codes_email", "email_codes", ["email"])


def downgrade() -> None:
    db = op.get_bind()
    if db.scalar(sa.text("SELECT count(*) FROM users WHERE email IS NOT NULL")) or db.scalar(
        sa.text("SELECT count(*) FROM email_codes")
    ):
        raise RuntimeError("Cannot discard email identities or verification history")
    op.drop_table("email_codes")
    op.drop_constraint("ck_user_email_normalized", "users", type_="check")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "email")
    op.alter_column("users", "username", existing_type=sa.String(80), nullable=False)
