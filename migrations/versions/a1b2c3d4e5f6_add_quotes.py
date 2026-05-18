"""add_quotes

Revision ID: a1b2c3d4e5f6
Revises: e93df22e96a2
Create Date: 2026-05-18 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'e93df22e96a2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'quote',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('text', sa.String(length=2000), nullable=False),
        sa.Column('page_ref', sa.String(length=20), nullable=True),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date_added', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('quote')
