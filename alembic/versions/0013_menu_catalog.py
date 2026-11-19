"""Rich menu catalogue metadata and non-destructive archival."""
from alembic import op
import sqlalchemy as sa
revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

def upgrade():
    for col in [sa.Column('catalog_slug',sa.String(100),nullable=True),sa.Column('description',sa.Text(),nullable=False,server_default=''),sa.Column('ingredients',sa.JSON(),nullable=False,server_default='[]'),sa.Column('dietary_tags',sa.JSON(),nullable=False,server_default='[]'),sa.Column('portion_value',sa.Integer(),nullable=True),sa.Column('portion_unit',sa.String(2),nullable=True),sa.Column('is_archived',sa.Boolean(),nullable=False,server_default=sa.false())]:
        op.add_column('menu_items',col)
    op.create_index('uq_menu_catalog_slug','menu_items',['catalog_slug'],unique=True)

def downgrade():
    op.drop_index('uq_menu_catalog_slug',table_name='menu_items')
    for name in ['is_archived','portion_unit','portion_value','dietary_tags','ingredients','description','catalog_slug']:
        op.drop_column('menu_items',name)
