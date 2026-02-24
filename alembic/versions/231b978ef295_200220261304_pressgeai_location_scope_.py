"""200220261304 (pressgeai) location scope column set to ENUM

Revision ID: 231b978ef295
Revises: ad39c7303c1b
Create Date: 2026-02-20 13:05:31.492454

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = '231b978ef295'
down_revision: Union[str, Sequence[str], None] = 'ad39c7303c1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

location_scope_enum = ENUM('city', 'state', 'country', 'international', 'unreviewed', name='location_scope_enum')

def upgrade():
    location_scope_enum.create(op.get_bind())  # create the type first
    op.alter_column('generated_user_stories', 'location_scope',
               existing_type=sa.VARCHAR(length=20),
               type_=ENUM('city', 'state', 'country', 'international', 'unreviewed', 
                          name='location_scope_enum', create_type=False),  # don't create again
               existing_nullable=True,
               postgresql_using="location_scope::location_scope_enum")  # cast existing data

def downgrade():
    op.alter_column('generated_user_stories', 'location_scope',
               existing_type=ENUM('city', 'state', 'country', 'international', 'unreviewed',
                                  name='location_scope_enum', create_type=False),
               type_=sa.VARCHAR(length=20),
               existing_nullable=True)
    location_scope_enum.drop(op.get_bind())
    # ### end Alembic commands ###
