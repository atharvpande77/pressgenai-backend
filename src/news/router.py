from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload, selectinload
from sqlalchemy import select, func, case, literal, or_, and_
from sqlalchemy.dialects.postgresql import JSONB
from uuid import UUID

from src.config.database import get_session, Session
from src.models import GeneratedUserStories, NewsCategory, UserStories, UserStoryPublishStatus, UserStoryStatus, Users, Authors
from src.news.dependencies import get_category_dep
from src.news.schemas import CreatorProfileResponse, ArticleListResponse, ArticleDetailResponse
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
    description="Retrieve a paginated list of all published articles with optional filtering by category or city.",
    responses={
        200: {"description": "List of articles retrieved successfully"},
        400: {"description": "Invalid category ID or city ID provided"},
    }
)
async def get_all_articles(
    session: Annotated[AsyncSession, Depends(get_session)],
    category_id: UUID | None = None,
    city_id: UUID | None = None,
    limit: Annotated[int | None, Query(gt=0, le=100)] = 10,
    offset: int| None = 0
):
    if city_id and not await session.get(Cities, city_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invalid city ID"
        )
        
    if category_id and not await session.get(Categories, category_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invalid category ID"
        )
    
    query = (
        select(GeneratedUserStories)
        .join(UserStories, GeneratedUserStories.user_story_id == UserStories.id)
        .where(
            UserStories.publish_status == UserStoryPublishStatus.PUBLISHED,
            UserStories.status == UserStoryStatus.SUBMITTED,
        )
        .options(
            selectinload(GeneratedUserStories.categories),
            selectinload(GeneratedUserStories.city),
            selectinload(GeneratedUserStories.author).selectinload(Authors.user),
            selectinload(GeneratedUserStories.editor),
        )
        .limit(limit)
        .offset(offset)
        .order_by(GeneratedUserStories.created_at.desc())
    )

    if city_id:
        query = query.where(GeneratedUserStories.city_id == city_id)

    if category_id:
        query = query.where(GeneratedUserStories.categories.any(Categories.id == category_id))
    
    result = await session.execute(query)
    article_rows = result.scalars().unique().all()

    return article_rows


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
        .options(
        selectinload(GeneratedUserStories.categories),
        selectinload(GeneratedUserStories.author).selectinload(Authors.user),
        selectinload(GeneratedUserStories.editor),
        selectinload(GeneratedUserStories.city),
        )
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
        .options(
            selectinload(GeneratedUserStories.categories),
            selectinload(GeneratedUserStories.city),
            selectinload(GeneratedUserStories.editor),
        )
        .where(
            GeneratedUserStories.author_id == creator_user.id,
            UserStories.publish_status == UserStoryPublishStatus.PUBLISHED,
            UserStories.status == UserStoryStatus.SUBMITTED,
        )
    )

    if sort_by == "newest" or sort_by == "popular":
        articles_query = articles_query.order_by(GeneratedUserStories.created_at.desc())
    elif sort_by == "oldest":
        articles_query = articles_query.order_by(GeneratedUserStories.created_at.asc())

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
        "articles": articles
    })
