"""add security question

Revision ID: c3d4e5f6a7b8
Revises: f1a2b3c4d5e6
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name'] for c in insp.get_columns('user')}
    cols_to_add = []
    if 'security_question' not in cols:
        cols_to_add.append(sa.Column('security_question', sa.String(length=200), nullable=True))
    if 'security_answer_hash' not in cols:
        cols_to_add.append(sa.Column('security_answer_hash', sa.String(length=256), nullable=True))
    if cols_to_add:
        with op.batch_alter_table('user', schema=None) as batch_op:
            for col in cols_to_add:
                batch_op.add_column(col)


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('security_answer_hash')
        batch_op.drop_column('security_question')
