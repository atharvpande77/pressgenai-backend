"""added title hash column and made title hash and author id unqiue together 011120251306

Revision ID: 14b623349711
Revises: 0a35ce913efa
Create Date: 2025-11-01 13:06:14.281955

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from hashlib import sha256
from sqlalchemy import text
import uuid

# revision identifiers, used by Alembic.
revision: str = '14b623349711'
down_revision: Union[str, Sequence[str], None] = '0a35ce913efa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Step 1: Add the new column as nullable
    op.add_column('generated_user_stories', sa.Column('title_hash', sa.String(64), nullable=True))

    conn = op.get_bind()

    # Step 2: Backfill title_hash for all rows
    # Handle duplicates by appending a short random string
    results = conn.execute(text("SELECT id, author_id, title FROM generated_user_stories")).fetchall()
    seen = set()

    for row in results:
        title = (row.title or '').strip().lower()
        base_hash = sha256(title.encode('utf-8')).hexdigest()

        # Combine author_id + hash to detect duplicates
        key = (str(row.author_id), base_hash)

        # If duplicate, randomize slightly to make unique
        if key in seen:
            base_hash = sha256((title + str(uuid.uuid4())).encode('utf-8')).hexdigest()

        seen.add(key)

        conn.execute(
            text("UPDATE generated_user_stories SET title_hash = :hash WHERE id = :id"),
            {"hash": base_hash, "id": row.id}
        )

    # Step 3: Enforce NOT NULL
    op.alter_column('generated_user_stories', 'title_hash', nullable=False)

    # Step 4: Add the unique constraint (author_id + title_hash)
    op.create_unique_constraint(
        'uq_author_titlehash',
        'generated_user_stories',
        ['author_id', 'title_hash']
    )


def downgrade():
    op.drop_constraint('uq_author_titlehash', 'generated_user_stories', type_='unique')
    op.drop_column('generated_user_stories', 'title_hash')
