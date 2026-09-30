"""add password_hash, roles, refresh_tokens

По шагам 1.2-1.4 методички. Существующим пользователям назначается роль student.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30 10:36:02.241418

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)

    # password_hash остаётся nullable навсегда: у пользователей из lab 2 и у тех,
    # кто входит через внешнего провайдера, пароля нет.
    op.add_column("users", sa.Column("password_hash", sa.String(), nullable=True))
    # role_id сначала nullable: в таблице уже есть строки, NOT NULL сразу упадёт.
    op.add_column("users", sa.Column("role_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_users_role_id_roles", "users", "roles", ["role_id"], ["id"])

    op.execute("INSERT INTO roles (name) VALUES ('student'), ('cook'), ('courier'), ('admin')")
    op.execute("UPDATE users SET role_id = (SELECT id FROM roles WHERE name = 'student')")
    op.alter_column("users", "role_id", nullable=False)


def downgrade() -> None:
    op.drop_constraint("fk_users_role_id_roles", "users", type_="foreignkey")
    op.drop_column("users", "role_id")
    op.drop_column("users", "password_hash")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("roles")
