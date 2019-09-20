"""tweak

Revision ID: 04cac43392e4
Revises: 6bae8b053819
Create Date: 2019-09-20 16:32:01.024163

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '04cac43392e4'
down_revision = '6bae8b053819'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('report_model', 'cross_trail',
               existing_type=sa.VARCHAR(length=16),
               nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('report_model', 'cross_trail',
               existing_type=sa.VARCHAR(length=16),
               nullable=False)
    # ### end Alembic commands ###
