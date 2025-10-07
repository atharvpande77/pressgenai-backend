"""make category column an array of enum 071020251737

Revision ID: 508ed4d9b703
Revises: abd57f2a0379
Create Date: 2025-10-07 17:37:36.533821

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY


# revision identifiers, used by Alembic.
revision: str = '508ed4d9b703'
down_revision: Union[str, Sequence[str], None] = 'abd57f2a0379'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

from src.models import news_category_enum, NewsCategory

table_name = 'generated_user_stories'
column_name = 'category'
old_enum_name = 'news_category'

new_enum_values = [category.value for category in NewsCategory]

def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        table_name,
        column_name,
        type_=sa.Text(),
        postgresql_using=f"{column_name}::text"
    )
    op.execute(f"DROP TYPE IF EXISTS {old_enum_name}")
    op.execute(f"CREATE TYPE {old_enum_name} AS ENUM ({', '.join(f"'{v}'" for v in new_enum_values)})")

    op.alter_column(
        table_name,
        column_name,
        type_=ARRAY(sa.Enum(*new_enum_values, name=old_enum_name)),
        postgresql_using=f"ARRAY[{column_name}]::{old_enum_name}[]"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        table_name,
        column_name,
        type_=sa.Enum(*new_enum_values, name=old_enum_name),
        postgresql_using=f"{column_name}[1]"
    )
