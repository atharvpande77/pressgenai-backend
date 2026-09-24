"""add position to article_categories

Revision ID: 5e2240391984
Revises: 9fac82ba9e76
Create Date: 2026-09-24 12:16:02.260004

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e2240391984'
down_revision: Union[str, Sequence[str], None] = '9fac82ba9e76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "article_categories",
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    # Backfill: category rows are written in one INSERT per edit, so physical row
    # order (ctid) reflects the order the categories were supplied in.
    op.execute(
        """
        UPDATE article_categories AS ac
        SET position = ordered.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY article_id ORDER BY ctid) - 1 AS rn
            FROM article_categories
        ) AS ordered
        WHERE ac.id = ordered.id
        """
    )
    op.create_index(
        "ix_article_categories_article_position",
        "article_categories",
        ["article_id", "position"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_article_categories_article_position", table_name="article_categories")
    op.drop_column("article_categories", "position")
