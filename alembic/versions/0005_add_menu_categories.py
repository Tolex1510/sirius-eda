"""add menu categories

Разделы меню для GET /menu/categories/{id}. Старые блюда остаются без категории.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17 15:54:42.062050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.add_column("menu_items", sa.Column("category_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_menu_items_category_id"), "menu_items", ["category_id"], unique=False)
    op.create_foreign_key(
        "fk_menu_items_category_id_categories", "menu_items", "categories", ["category_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_menu_items_category_id_categories", "menu_items", type_="foreignkey")
    op.drop_index(op.f("ix_menu_items_category_id"), table_name="menu_items")
    op.drop_column("menu_items", "category_id")
    op.drop_table("categories")
