"""add book reading timeline dates

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-07-11

Additive-only: adds Book.started_reading_at and Book.finished_reading_at
as nullable DATE columns. Existing rows remain NULL (no backfill).
No drops, renames, nullability changes, or data resets.
Users, quotes, ratings, Wild flags, covers, and reading statuses are untouched.
"""
from alembic import op
import sqlalchemy as sa


revision = 'h8i9j0k1l2m3'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name'] for c in insp.get_columns('book')}
    with op.batch_alter_table('book', schema=None) as batch_op:
        if 'started_reading_at' not in cols:
            batch_op.add_column(
                sa.Column('started_reading_at', sa.Date(), nullable=True)
            )
        if 'finished_reading_at' not in cols:
            batch_op.add_column(
                sa.Column('finished_reading_at', sa.Date(), nullable=True)
            )


def downgrade():
    with op.batch_alter_table('book', schema=None) as batch_op:
        batch_op.drop_column('finished_reading_at')
        batch_op.drop_column('started_reading_at')
