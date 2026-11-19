"""Rebuild the derived knowledge index for bge-m3's 1024-dimensional embeddings."""
from alembic import op
revision='0014'
down_revision='0013'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('DELETE FROM knowledge_chunks')
    op.execute('ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(1024)')

def downgrade():
    op.execute('DELETE FROM knowledge_chunks')
    op.execute('ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(768)')
