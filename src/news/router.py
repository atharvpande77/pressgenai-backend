from fastapi import APIRouter, Depends, HTTPException, Response, status, Query
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Load, aliased, joinedload, selectinload
from sqlalchemy import select, func, case, literal, or_, and_
from sqlalchemy.dialects.postgresql import JSONB
from uuid import UUID

from src.config.database import get_session, Session
from src.models import GeneratedUserStories, NewsCategory, UserStories, UserStoryPublishStatus, UserStoryStatus, Users, Authors
from src.news.dependencies import get_category_dep
from src.news.schemas import (
    CreatorProfileResponse,
    ArticleListResponse,
    ArticleDetailResponse,
    SitemapArticleResponse,
    SitemapAuthorResponse,
)
from src.news import service as news_service
from src.aws.utils import get_bucket_base_url
from src.news.utils import get_category_name

router = APIRouter()

Creators = aliased(Users)
Editors = aliased(Users)

from src.models import Cities, Categories

@router.get(
    '/', 
    response_model=list[ArticleListResponse],
    summary="Get all articles",
    description=(
        "Retrieve a paginated list of published articles, newest first, optionally filtered by "
        "category (`category_id` UUID or `category` slug, e.g. `local-news`) and/or city "
        "(`city_id` UUID or `city` slug, e.g. `nagpur`). The total number of matching articles "
        "is returned in the `X-Total-Count` header."
    ),
    responses={
        200: {"description": "List of articles retrieved successfully"},
        400: {"description": "Invalid category or city provided"},
    }
)
async def get_all_articles(
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
    category_id: UUID | None = None,
    city_id: UUID | None = None,
    category: Annotated[str | None, Query(description="Category slug, e.g. local-news")] = None,
    city: Annotated[str | None, Query(description="City slug, e.g. nagpur")] = None,
    limit: Annotated[int | None, Query(gt=0, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    resolved_category_id = await news_service.resolve_category_filter(session, category_id, category)
    resolved_city_id = await news_service.resolve_city_filter(session, city_id, city)
    articles, total = await news_service.list_published_articles(
        session,
        category_id=resolved_category_id,
        city_id=resolved_city_id,
        limit=limit,
        offset=offset,
    )
    response.headers["X-Total-Count"] = str(total)
    return articles


@router.get(
    '/sitemap',
    response_model=list[SitemapArticleResponse],
    summary="Published article URLs for sitemaps",
    description="Lightweight list (slug, primary category, timestamps) of published articles, newest first. Total in `X-Total-Count`.",
)
async def get_sitemap_articles(
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
    limit: Annotated[int, Query(gt=0, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    rows, total = await news_service.list_sitemap_entries(session, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get(
    '/authors',
    response_model=list[SitemapAuthorResponse],
    summary="Creators with published articles",
    description="Usernames of active creators with at least one published article and the time of their latest article.",
)
async def get_published_authors(session: Annotated[AsyncSession, Depends(get_session)]):
    rows = await news_service.list_published_authors(session)
    return [{"username": username, "lastmod": lastmod} for username, lastmod in rows]


@router.get(
    '/{article_slug_or_id}',
    response_model=ArticleDetailResponse,
    summary="Get article by slug or ID",
    description="Retrieve a detailed article by its slug or UUID. The article must be published to be accessible.",
    responses={
        200: {"description": "Article retrieved successfully"},
        404: {"description": "Article not found for the provided identifier"},
    }
)
async def get_article_by_slug_or_id(
    session: Annotated[AsyncSession, Depends(get_session)],
    article_slug_or_id: str
):
    filters = [GeneratedUserStories.slug == article_slug_or_id]
    try:
        article_id = UUID(article_slug_or_id)
        filters.append(GeneratedUserStories.id == article_id)
    except ValueError:
        pass

    result = await session.execute(
        select(GeneratedUserStories)
        .join(UserStories, GeneratedUserStories.user_story_id == UserStories.id)
        .options(*news_service.article_load_options())
        .where(
            or_(*filters),
            UserStories.publish_status == UserStoryPublishStatus.PUBLISHED,
            UserStories.status == UserStoryStatus.SUBMITTED,
        )
        .limit(1)
    )
    article = result.scalars().first()
    if not article:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f'no article found for identifier {article_slug_or_id}'
        )
    
    return article

@router.get(
    '/creator/{creator_username_or_id}',
    response_model=CreatorProfileResponse,
    summary="Get creator profile",
    description="Retrieve a creator's profile with their published articles. Articles can be sorted by newest, oldest, or popular.",
    responses={
        200: {"description": "Creator profile retrieved successfully"},
        404: {"description": "Creator not found for the provided identifier"},
    }
)
async def get_creator_profile(
    session: Annotated[AsyncSession, Depends(get_session)],
    creator_username_or_id: str,
    sort_by: Annotated[str, Query(pattern="^(newest|oldest|popular)$")] = "newest",
    limit: Annotated[int, Query(gt=0, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    identifier_filters = [Users.username == creator_username_or_id]
    try:
        creator_id = UUID(creator_username_or_id)
        identifier_filters.append(Users.id == creator_id)
    except ValueError:
        pass

    result = await session.execute(
        select(Users, Authors)
        .join(Authors, Authors.id == Users.id)
        # Only the two rows themselves; their selectin relationships would load the author's whole history.
        .options(Load(Users).lazyload("*"), Load(Authors).lazyload("*"))
        .where(
            and_(
                Users.active == True,
                or_(*identifier_filters),
            )
        )
        .limit(1)
    )
    creator_row = result.first()
    
    if not creator_row:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="creator not found"
        )
    creator_user, creator = creator_row

    articles_query = (
        select(GeneratedUserStories)
        .join(UserStories, GeneratedUserStories.user_story_id == UserStories.id)
        .options(*news_service.article_load_options(author=False))
        .where(
            GeneratedUserStories.author_id == creator_user.id,
            UserStories.publish_status == UserStoryPublishStatus.PUBLISHED,
            UserStories.status == UserStoryStatus.SUBMITTED,
        )
    )

    if sort_by == "newest" or sort_by == "popular":
        articles_query = news_service.newest_first(articles_query)
    elif sort_by == "oldest":
        articles_query = articles_query.order_by(
            GeneratedUserStories.published_at.asc().nulls_last(),
            GeneratedUserStories.created_at.asc(),
        )

    articles_query = articles_query.limit(limit).offset(offset)

    result = await session.execute(articles_query)
    articles = result.scalars().unique().all()

    return CreatorProfileResponse.model_validate({
        "id": creator_user.id,
        "creator_username": creator_user.username,
        "username": creator_user.username,
        "first_name": creator_user.first_name,
        "last_name": creator_user.last_name,
        "bio": creator.bio,
        "profile_image_key": creator_user.profile_image_key,
        "total_count": await news_service.count_published_articles_by_author(session, creator_user.id),
        "articles": articles
    })
