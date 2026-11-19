"""Flag exhausted provider checks for explicit operator review.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa
revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('payments', sa.Column('review_required', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    op.drop_column('payments', 'review_required')
