"""Persist provider cancellation reason for payment_failed scenarios.

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('payments', sa.Column('cancellation_reason', sa.String(100), nullable=True))


def downgrade():
    op.drop_column('payments', 'cancellation_reason')
