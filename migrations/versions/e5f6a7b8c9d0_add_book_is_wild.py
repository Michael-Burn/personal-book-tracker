"""add book is_wild

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-11

Additive-only: adds Book.is_wild BOOLEAN NOT NULL DEFAULT FALSE.
Existing rows receive False via server_default. No drops, renames, or data resets.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name'] for c in insp.get_columns('book')}
    if 'is_wild' not in cols:
        with op.batch_alter_table('book', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    'is_wild',
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )


def downgrade():
    with op.batch_alter_table('book', schema=None) as batch_op:
        batch_op.drop_column('is_wild')
