"""add orders total_cost

Нужна для возврата денег при отмене заказа. Старым заказам сумма
восстанавливается по текущей цене блюда: исторической цены в lab 2 не хранили.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30 10:39:12.261361

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("total_cost", sa.Float(), nullable=True))
    op.execute(
        "UPDATE orders SET total_cost = orders.quantity * menu_items.price "
        "FROM menu_items WHERE menu_items.id = orders.item_id"
    )
    op.execute("UPDATE orders SET total_cost = 0 WHERE total_cost IS NULL")
    op.alter_column("orders", "total_cost", nullable=False)


def downgrade() -> None:
    op.drop_column("orders", "total_cost")
