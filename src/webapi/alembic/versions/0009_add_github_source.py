"""add repositories.github_project_id

GitHub source type ("github") alongside upload/gitlab. The repo URL column stays
gitlab_url (generic remote URL, keeps migrations minimal); github_project_id holds
"owner/repo" for webhook matching (GitHub sends the repo full_name, not a numeric id).

Revision ID: 0009_github_source
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_github_source"  # <=32 chars (alembic_version.version_num width)
down_revision = "0008_run_secrets_job_cookie"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_column("repositories", "github_project_id"):
        op.add_column(
            "repositories",
            sa.Column("github_project_id", sa.String(100), nullable=True),
        )


def downgrade() -> None:
    if _has_column("repositories", "github_project_id"):
        op.drop_column("repositories", "github_project_id")
