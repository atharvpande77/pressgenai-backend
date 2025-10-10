"""added profile image key and active columns

Revision ID: 9d4620f55043
Revises: 508ed4d9b703
Create Date: 2025-10-08 22:43:32.407907

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '9d4620f55043'
down_revision: Union[str, Sequence[str], None] = '508ed4d9b703'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema safely."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]

    if 'profile_image_key' not in columns:
        op.add_column('users', sa.Column('profile_image_key', sa.String(), nullable=True))
    
    if 'active' not in columns:
        op.add_column('users', sa.Column('active', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema safely."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]

    if 'profile_image_key' in columns:
        op.drop_column('users', 'profile_image_key')
    
    if 'active' in columns:
        op.drop_column('users', 'active')
