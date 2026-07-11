"""add quote is_favourite

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-07-12

Additive-only: adds Quote.is_favourite BOOLEAN NOT NULL DEFAULT FALSE
and a partial unique index so each user has at most one favourite.
Existing quotes receive False. No drops, renames, or data resets.
"""
from alembic import op
import sqlalchemy as sa


revision = 'j0k1l2m3n4o5'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name'] for c in insp.get_columns('quote')}
    if 'is_favourite' not in cols:
        with op.batch_alter_table('quote', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    'is_favourite',
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )

    # Refresh inspector after possible column add
    insp = sa.inspect(bind)
    indexes = {ix['name'] for ix in insp.get_indexes('quote')}
    if 'uq_quote_one_favourite_per_user' not in indexes:
        dialect = bind.dialect.name
        # Partial unique index only — never a full unique on user_id.
        if dialect == 'postgresql':
            op.create_index(
                'uq_quote_one_favourite_per_user',
                'quote',
                ['user_id'],
                unique=True,
                postgresql_where=sa.text('is_favourite IS TRUE'),
            )
        elif dialect == 'sqlite':
            op.create_index(
                'uq_quote_one_favourite_per_user',
                'quote',
                ['user_id'],
                unique=True,
                sqlite_where=sa.text('is_favourite = 1'),
            )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    indexes = {ix['name'] for ix in insp.get_indexes('quote')}
    if 'uq_quote_one_favourite_per_user' in indexes:
        op.drop_index('uq_quote_one_favourite_per_user', table_name='quote')
    cols = {c['name'] for c in insp.get_columns('quote')}
    if 'is_favourite' in cols:
        with op.batch_alter_table('quote', schema=None) as batch_op:
            batch_op.drop_column('is_favourite')
