"""avatar_column_to_text

Revision ID: b7c1d2e3f4a5
Revises: e93df22e96a2
Create Date: 2026-05-18 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b7c1d2e3f4a5'
down_revision = 'e93df22e96a2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column(
            'avatar',
            existing_type=sa.String(length=120),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column(
            'avatar',
            existing_type=sa.Text(),
            type_=sa.String(length=120),
            existing_nullable=True,
        )
