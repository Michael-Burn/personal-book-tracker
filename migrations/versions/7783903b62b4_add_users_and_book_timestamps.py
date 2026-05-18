"""add_users_and_book_timestamps

Revision ID: 7783903b62b4
Revises: 
Create Date: 2026-05-18 16:57:14.894294

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7783903b62b4'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if 'user' not in existing_tables:
        op.create_table(
            'user',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('username', sa.String(length=80), nullable=False),
            sa.Column('password_hash', sa.String(length=256), nullable=False),
            sa.Column('is_admin', sa.Boolean(), nullable=False),
            sa.Column('plan', sa.String(length=20), nullable=False),
            sa.Column('stripe_customer_id', sa.String(length=120), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        with op.batch_alter_table('user', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_user_username'), ['username'], unique=True)

    if 'book' not in existing_tables:
        op.create_table(
            'book',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=False),
            sa.Column('author', sa.String(length=200), nullable=False),
            sa.Column('rating', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('date_added', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['user.id']),
            sa.PrimaryKeyConstraint('id'),
        )
    else:
        # Table already existed before migrations were introduced — add missing columns.
        existing_cols = {c['name'] for c in insp.get_columns('book')}
        cols_to_add = []
        if 'user_id' not in existing_cols:
            cols_to_add.append(sa.Column('user_id', sa.Integer(), nullable=True))
        if 'date_added' not in existing_cols:
            cols_to_add.append(sa.Column('date_added', sa.DateTime(), nullable=True))
        if cols_to_add:
            with op.batch_alter_table('book', schema=None) as batch_op:
                for col in cols_to_add:
                    batch_op.add_column(col)


def downgrade():
    op.drop_table('book')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_username'))
    op.drop_table('user')
