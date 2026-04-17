"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("email", sa.String(120)),
        sa.Column("role", sa.String(20), server_default="user"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("blob_url", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("doc_type", sa.String(50)),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime()),
        sa.Column("error_message", sa.Text()),
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("vendor_name", sa.String(200)),
        sa.Column("vendor_address", sa.Text()),
        sa.Column("invoice_number", sa.String(100)),
        sa.Column("invoice_date", sa.Date()),
        sa.Column("due_date", sa.Date()),
        sa.Column("subtotal", sa.Numeric(12, 2)),
        sa.Column("tax_amount", sa.Numeric(12, 2)),
        sa.Column("total_amount", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(10), server_default="INR"),
        sa.Column("payment_status", sa.String(20), server_default="unpaid"),
        sa.Column("doc_type", sa.String(20)),
        sa.Column("notes", sa.Text()),
        sa.Column("raw_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "line_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("quantity", sa.Numeric(10, 2)),
        sa.Column("unit_price", sa.Numeric(12, 2)),
        sa.Column("line_total", sa.Numeric(12, 2)),
    )

    op.create_table(
        "query_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("sql_generated", sa.Text()),
        sa.Column("answer", sa.Text()),
        sa.Column("was_voice", sa.Boolean(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("query_log")
    op.drop_table("line_items")
    op.drop_table("invoices")
    op.drop_table("documents")
    op.drop_table("users")
