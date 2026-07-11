"""add reading_goal table

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-07-11

Additive-only: creates reading_goal (one annual target per user per year).
Existing users, books, quotes, and all book columns are untouched.
No drops, renames, nullability changes, or data resets.
"""
from alembic import op
import sqlalchemy as sa


revision = 'i9j0k1l2m3n4'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'reading_goal' not in insp.get_table_names():
        op.create_table(
            'reading_goal',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('year', sa.Integer(), nullable=False),
            sa.Column('target_count', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['user.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'year', name='uq_reading_goal_user_year'),
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'reading_goal' in insp.get_table_names():
        op.drop_table('reading_goal')
