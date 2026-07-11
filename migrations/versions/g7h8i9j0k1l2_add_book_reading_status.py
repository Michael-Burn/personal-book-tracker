"""add book reading_status

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-11

Additive-only: adds Book.reading_status VARCHAR(20) NOT NULL DEFAULT 'finished'.
Existing rows automatically receive 'finished' via server_default.
No drops, renames, nullability changes, or data resets.
Ratings, Wild flags, covers, quotes, and users are untouched.
"""
from alembic import op
import sqlalchemy as sa


revision = 'g7h8i9j0k1l2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name'] for c in insp.get_columns('book')}
    if 'reading_status' not in cols:
        with op.batch_alter_table('book', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    'reading_status',
                    sa.String(length=20),
                    nullable=False,
                    server_default='finished',
                )
            )


def downgrade():
    with op.batch_alter_table('book', schema=None) as batch_op:
        batch_op.drop_column('reading_status')
