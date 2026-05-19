"""add blob_name to documents

Revision ID: 002
Revises: 001
Create Date: 2026-05-19

blob_name stores the bare blob key (uuid-filename) so the app can
stream file bytes directly to Document Intelligence instead of passing
the blob URL — the container is private so the URL is not publicly
accessible.
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents",
        sa.Column("blob_name", sa.String(500), nullable=True),
    )


def downgrade():
    op.drop_column("documents", "blob_name")
