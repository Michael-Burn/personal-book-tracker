"""merge migration heads

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8, b7c1d2e3f4a5
Create Date: 2026-07-11
"""
# Merge the security-question chain and the avatar-to-text branch
# so a single linear history exists before additive schema changes.

revision = 'd4e5f6a7b8c9'
down_revision = ('c3d4e5f6a7b8', 'b7c1d2e3f4a5')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
