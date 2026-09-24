"""Throttle login attempts for registered and unregistered emails alike."""

import sqlalchemy as sa
from alembic import op

revision = "g034_login_attempts"
down_revision = "f033_email_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("email", sa.String(254), primary_key=True),
        sa.Column("failed_logins", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
    )
    op.execute(
        sa.text(
            "INSERT INTO login_attempts (email, failed_logins, locked_until) "
            "SELECT email, failed_logins, locked_until FROM users "
            "WHERE email IS NOT NULL AND (failed_logins > 0 OR locked_until IS NOT NULL)"
        )
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM login_attempts")):
        raise RuntimeError("Cannot discard login throttle history")
    op.drop_table("login_attempts")
