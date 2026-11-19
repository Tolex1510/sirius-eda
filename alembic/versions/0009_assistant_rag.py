"""Public pgvector index and user-scoped conversation history.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.create_table('knowledge_chunks',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('url', sa.String(512), nullable=False),
        sa.Column('checksum', sa.String(64), nullable=False),
        sa.Column('embedding', Vector(768), nullable=False),
        sa.Column('embedding_model', sa.String(100), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('chat_conversations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_chat_conversations_user_id', 'chat_conversations', ['user_id'])
    op.create_table('chat_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('chat_conversations.id'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('sources', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_chat_messages_conversation_id', 'chat_messages', ['conversation_id'])


def downgrade():
    op.drop_index('ix_chat_messages_conversation_id', table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_index('ix_chat_conversations_user_id', table_name='chat_conversations')
    op.drop_table('chat_conversations')
    op.drop_table('knowledge_chunks')
    # Расширение может использоваться другими таблицами: не удаляем его.
