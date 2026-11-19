"""Decimal amounts, explicit payment source, persistent payment intentions.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    for table, column in [('users', 'balance'), ('menu_items', 'price'), ('orders', 'total_cost'), ('order_stats', 'revenue')]:
        op.alter_column(table, column, type_=sa.Numeric(14, 2), existing_type=sa.Float(),
                        postgresql_using=f'round({column}::numeric, 2)')
    op.add_column('orders', sa.Column('payment_source', sa.String(20), nullable=False, server_default='internal_balance'))
    op.create_table('payments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id'), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('amount', sa.Numeric(14, 2), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('idempotency_key', sa.String(64), nullable=False),
        sa.Column('gateway_id', sa.String(100), unique=True),
        sa.Column('confirmation_url', sa.String(2048)),
        sa.Column('refund_status', sa.String(20)),
        sa.Column('refund_id', sa.String(100)),
        sa.Column('refund_started_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('user_id', 'idempotency_key', name='uq_payments_user_key'))
    op.create_index('ix_payments_user_id', 'payments', ['user_id'])


def downgrade():
    op.drop_index('ix_payments_user_id', table_name='payments')
    op.drop_table('payments')
    op.drop_column('orders', 'payment_source')
    for table, column in [('users', 'balance'), ('menu_items', 'price'), ('orders', 'total_cost'), ('order_stats', 'revenue')]:
        op.alter_column(table, column, type_=sa.Float(), existing_type=sa.Numeric(14, 2), postgresql_using=f'{column}::double precision')
