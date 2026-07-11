"""add book cover_filename

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-11

Additive-only: adds Book.cover_filename VARCHAR(255) nullable.
Existing rows remain NULL (no cover). No drops, renames, or data resets.
"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name'] for c in insp.get_columns('book')}
    if 'cover_filename' not in cols:
        with op.batch_alter_table('book', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('cover_filename', sa.String(length=255), nullable=True)
            )


def downgrade():
    with op.batch_alter_table('book', schema=None) as batch_op:
        batch_op.drop_column('cover_filename')
