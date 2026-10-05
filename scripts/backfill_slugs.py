"""
Backfill English slugs for articles whose slug is missing or not plain ASCII.

    python -m scripts.backfill_slugs --dry-run --out /out          # default: no writes
    python -m scripts.backfill_slugs --apply --limit 5 --out /out  # small real run
    python -m scripts.backfill_slugs --apply --out /out

Groups:
    A  slug IS NULL                                  -> written with --apply
    B  non-ASCII slug, article not published         -> written with --apply
    C  non-ASCII slug, article published             -> reported only (changing it breaks live URLs)

The new slug is built from an English title (`ensure_english_title`), exactly like new articles.
Rows with no title or no obtainable English title are skipped and left unchanged, so re-running is safe.
A CSV of old -> new slugs is written to --out and doubles as the rollback record.
"""
import argparse
import asyncio
import csv
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, update

from src.config.database import async_session
from src.models import GeneratedUserStories, UserStories, UserStoryPublishStatus
from src.stories.service import generate_unique_slug
from src.stories.utils import ensure_english_title

logger = logging.getLogger("backfill_slugs")

VALID_SLUG_REGEX = r'^[a-z0-9]+(-[a-z0-9]+)*$'
BATCH_SIZE = 50


async def fetch_candidates(session):
    result = await session.execute(
        select(
            GeneratedUserStories.id,
            GeneratedUserStories.title,
            GeneratedUserStories.english_title,
            GeneratedUserStories.slug,
            UserStories.publish_status,
        )
        .join(UserStories, UserStories.id == GeneratedUserStories.user_story_id)
        .where(
            GeneratedUserStories.slug.is_(None)
            | GeneratedUserStories.slug.op("!~")(VALID_SLUG_REGEX)
        )
        .order_by(GeneratedUserStories.created_at)
    )
    return result.all()


def group_of(row) -> str:
    if row.slug is None:
        return "A"
    return "C" if row.publish_status == UserStoryPublishStatus.PUBLISHED.value else "B"


async def main(apply: bool, limit: int | None, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    changes, skipped = [], []

    async with async_session() as session:
        rows = await fetch_candidates(session)
        groups = {"A": [], "B": [], "C": []}
        for row in rows:
            groups[group_of(row)].append(row)
        print(f"A (no slug): {len(groups['A'])} | B (non-ASCII, unpublished): {len(groups['B'])} | "
              f"C (non-ASCII, published, NOT touched): {len(groups['C'])}")

        todo = groups["A"] + groups["B"]
        if limit:
            todo = todo[:limit]

        for index, row in enumerate(todo, start=1):
            if not (row.title and row.title.strip()):
                skipped.append((row.id, row.slug, "empty title"))
                continue
            try:
                english_title = await ensure_english_title(row.title, row.english_title)
            except ValueError:
                skipped.append((row.id, row.slug, "no English title obtained"))
                continue

            new_slug = await generate_unique_slug(session, english_title)
            changes.append((row.id, row.slug, new_slug, english_title))

            if apply:
                await session.execute(
                    update(GeneratedUserStories)
                    .where(GeneratedUserStories.id == row.id)
                    .values(slug=new_slug, english_title=english_title)
                )
                if index % BATCH_SIZE == 0:
                    await session.commit()
                    print(f"committed {index}/{len(todo)}")
        if apply:
            await session.commit()

    mode = "apply" if apply else "dry-run"
    changes_path = out_dir / f"slug-backfill-{mode}-{stamp}.csv"
    with changes_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "old_slug", "new_slug", "english_title"])
        writer.writerows(changes)
    skipped_path = out_dir / f"slug-backfill-skipped-{stamp}.csv"
    with skipped_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "old_slug", "reason"])
        writer.writerows(skipped)

    print(f"{mode}: {len(changes)} {'updated' if apply else 'would be updated'}, {len(skipped)} skipped")
    print(f"changes: {changes_path}\nskipped: {skipped_path}")
    for row_id, old, new, _ in changes[:10]:
        print(f"  {row_id}: {old!r} -> {new!r}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="show what would change (default)")
    mode.add_argument("--apply", action="store_true", help="write the new slugs")
    parser.add_argument("--limit", type=int, default=None, help="only process the first N rows of groups A+B")
    parser.add_argument("--out", type=Path, default=Path("."), help="directory for the CSV reports")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(apply=args.apply, limit=args.limit, out_dir=args.out))
