import re
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import (
    Authors,
    Categories,
    Cities,
    GeneratedUserStories,
    UserStories,
    UserStoryPublishStatus,
    UserStoryStatus,
    Users,
)


def slugify_city_name(name: str) -> str:
    """URL slug of a city name ("Nagpur" → "nagpur"); matches the frontend's city URLs."""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def published_articles() -> Select:
    """Base query: articles visible on the public site."""
    return (
        select(GeneratedUserStories)
        .join(UserStories, GeneratedUserStories.user_story_id == UserStories.id)
        .where(
            UserStories.publish_status == UserStoryPublishStatus.PUBLISHED,
            UserStories.status == UserStoryStatus.SUBMITTED,
        )
    )


def newest_first(query: Select) -> Select:
    return query.order_by(
        GeneratedUserStories.published_at.desc().nulls_last(),
        GeneratedUserStories.created_at.desc(),
        GeneratedUserStories.id,
    )


async def resolve_category_filter(session: AsyncSession, category_id: UUID | None, category: str | None) -> UUID | None:
    """Accepts a category UUID or its `value` slug (e.g. "local-news")."""
    if category_id:
        if not await session.get(Categories, category_id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid category ID")
        return category_id
    if category:
        result = await session.execute(select(Categories.id).where(Categories.value == category.strip().lower()))
        found = result.scalars().first()
        if not found:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid category")
        return found
    return None


async def resolve_city_filter(session: AsyncSession, city_id: UUID | None, city: str | None) -> UUID | None:
    """Accepts a city UUID or its URL slug (e.g. "nagpur")."""
    if city_id:
        if not await session.get(Cities, city_id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid city ID")
        return city_id
    if city:
        wanted = slugify_city_name(city)
        result = await session.execute(select(Cities.id, Cities.name))
        for found_id, name in result.all():
            if slugify_city_name(name) == wanted:
                return found_id
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid city")
    return None


async def list_published_articles(
    session: AsyncSession,
    *,
    category_id: UUID | None,
    city_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[GeneratedUserStories], int]:
    """A page of published articles (newest first) and the total matching count."""
    query = published_articles()
    if city_id:
        query = query.where(GeneratedUserStories.city_id == city_id)
    if category_id:
        query = query.where(GeneratedUserStories.categories.any(Categories.id == category_id))

    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()

    page_query = (
        newest_first(query)
        .options(
            selectinload(GeneratedUserStories.categories),
            selectinload(GeneratedUserStories.city),
            selectinload(GeneratedUserStories.author).selectinload(Authors.user),
            selectinload(GeneratedUserStories.editor),
        )
        .limit(limit)
        .offset(offset)
    )
    articles = (await session.execute(page_query)).scalars().unique().all()
    return list(articles), total


async def count_published_articles_by_author(session: AsyncSession, author_id: UUID) -> int:
    query = published_articles().where(GeneratedUserStories.author_id == author_id)
    return (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()


async def list_sitemap_entries(session: AsyncSession, *, limit: int, offset: int) -> tuple[list[GeneratedUserStories], int]:
    """Lightweight rows for sitemaps: slug, categories and timestamps only."""
    query = published_articles()
    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (
        await session.execute(
            newest_first(query)
            .options(selectinload(GeneratedUserStories.categories))
            .limit(limit)
            .offset(offset)
        )
    ).scalars().unique().all()
    return list(rows), total


async def list_published_authors(session: AsyncSession) -> list[tuple[str, datetime | None]]:
    """Usernames of active creators with at least one published article, and their latest article time."""
    latest = func.max(func.coalesce(GeneratedUserStories.updated_at, GeneratedUserStories.published_at))
    subquery = published_articles().subquery()
    result = await session.execute(
        select(Users.username, latest.label("lastmod"))
        .join(GeneratedUserStories, GeneratedUserStories.author_id == Users.id)
        .where(GeneratedUserStories.id.in_(select(subquery.c.id)), Users.active == True, Users.username.is_not(None))  # noqa: E712
        .group_by(Users.username)
        .order_by(latest.desc())
    )
    return [(username, lastmod) for username, lastmod in result.all()]
