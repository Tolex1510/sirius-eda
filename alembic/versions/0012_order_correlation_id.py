"""Persist order correlation IDs so asynchronous payment events retain business context.

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("orders", sa.Column("correlation_id", sa.String(length=128), nullable=True))


def downgrade():
    op.drop_column("orders", "correlation_id")
