"""add task_logs, order_stats and orders.created_at

Журнал фоновых задач для идемпотентности, сводка заказов для Celery Beat.
У старых заказов время создания неизвестно, им ставится время миграции.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-19 12:40:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "task_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "kind", name="uq_task_logs_order_id_kind"),
    )
    op.create_index(op.f("ix_task_logs_created_at"), "task_logs", ["created_at"], unique=False)
    op.create_table(
        "order_stats",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("orders", sa.Integer(), nullable=False),
        sa.Column("revenue", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("day"),
    )


def downgrade() -> None:
    op.drop_table("order_stats")
    op.drop_index(op.f("ix_task_logs_created_at"), table_name="task_logs")
    op.drop_table("task_logs")
    op.drop_column("orders", "created_at")
