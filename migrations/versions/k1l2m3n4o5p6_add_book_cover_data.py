"""add book cover_data column

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-07-12

Additive-only: adds Book.cover_data TEXT for storing book covers as WEBP
data-URIs in the database. Covers stored this way survive Render redeploys
because they live in PostgreSQL rather than on the ephemeral filesystem.
Existing books with cover_filename continue to work unchanged.
"""
from alembic import op
import sqlalchemy as sa


revision = 'k1l2m3n4o5p6'
down_revision = 'j0k1l2m3n4o5'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name'] for c in insp.get_columns('book')}
    if 'cover_data' not in cols:
        with op.batch_alter_table('book', schema=None) as batch_op:
            batch_op.add_column(sa.Column('cover_data', sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name'] for c in insp.get_columns('book')}
    if 'cover_data' in cols:
        with op.batch_alter_table('book', schema=None) as batch_op:
            batch_op.drop_column('cover_data')
