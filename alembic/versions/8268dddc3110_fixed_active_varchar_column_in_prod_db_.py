"""fixed active varchar column in prod db in users table 261120251851

Revision ID: 8268dddc3110
Revises: b37cc1df325d
Create Date: 2025-11-26 18:52:01.739727

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '8268dddc3110'
down_revision: Union[str, Sequence[str], None] = 'b37cc1df325d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Convert VARCHAR → BOOLEAN safely

def upgrade():
    conn = op.get_bind()

    # Must wrap SQL in text()
    result = conn.execute(
        text("""
            SELECT data_type 
            FROM information_schema.columns
            WHERE table_name = 'users'
            AND column_name = 'active'
        """)
    )

    col_type = result.scalar()

    # Convert only if not already boolean
    if col_type != "boolean":
        op.execute(text("""
            ALTER TABLE users
            ALTER COLUMN active TYPE boolean
            USING 
                CASE
                    WHEN active ILIKE 'true' THEN TRUE
                    WHEN active ILIKE 't' THEN TRUE
                    WHEN active ILIKE '1' THEN TRUE
                    WHEN active ILIKE 'yes' THEN TRUE
                    WHEN active ILIKE 'y' THEN TRUE
                    ELSE FALSE
                END;
        """))


def downgrade():
    conn = op.get_bind()

    result = conn.execute(
        text("""
            SELECT data_type 
            FROM information_schema.columns
            WHERE table_name = 'users'
            AND column_name = 'active'
        """)
    )

    col_type = result.scalar()

    if col_type == "boolean":
        op.execute(text("""
            ALTER TABLE users
            ALTER COLUMN active TYPE varchar;
        """))
