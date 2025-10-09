from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload, selectinload
from sqlalchemy import select, func

from src.config.database import get_session
from src.models import GeneratedUserStories, NewsCategory, UserStories, UserStoryPublishStatus, Users, Authors
from src.news.dependencies import get_category_dep
from src.news.schemas import CreatorProfileResponse, ArticleResponse

router = APIRouter()

Creators = aliased(Users)
Editors = aliased(Users)

@router.get('/', response_model=list[ArticleResponse])
async def get_all_articles(
    session: Annotated[AsyncSession, Depends(get_session)],
    category: Annotated[NewsCategory | None, Depends(get_category_dep)] = None,
    limit: Annotated[int | None, Query(gt=0, le=100)] = 10,
    offset: int| None = 0
):
    where_clause = (
        (GeneratedUserStories.category.contains([category]), UserStories.publish_status == UserStoryPublishStatus.PUBLISHED) 
        if category 
        else (UserStories.publish_status == UserStoryPublishStatus.PUBLISHED,)
    )
    result = await session.execute(
        select(
            GeneratedUserStories.id,
            GeneratedUserStories.title,
            GeneratedUserStories.snippet,
            GeneratedUserStories.full_text,
            GeneratedUserStories.created_at,
            GeneratedUserStories.updated_at,
            GeneratedUserStories.category,
            GeneratedUserStories.tags,
            GeneratedUserStories.slug,
            Creators.username.label("creator_username"),
            Creators.first_name.label("creator_first_name"),
            Creators.last_name.label("creator_last_name"),
            Editors.first_name.label("editor_first_name"),
            Editors.last_name.label("editor_last_name")
        )
            .join(UserStories, onclause=UserStories.id == GeneratedUserStories.user_story_id)
            .join(Creators, onclause=Creators.id == GeneratedUserStories.author_id)
            .join(Editors, onclause=Editors.id == GeneratedUserStories.editor_id, isouter=True)
            .where(*where_clause)
            .limit(limit)
            .offset(offset)
    )
    articles = result.all()
    return articles


@router.get('/categories')
async def get_all_categories():
    return [cat.value.title() for cat in NewsCategory]


@router.get('/{article_slug}', response_model=ArticleResponse)
async def get_article_by_id(
    session: Annotated[AsyncSession, Depends(get_session)],
    article_slug: str
):
    
    result = await session.execute(
        select(
            GeneratedUserStories.id,
            GeneratedUserStories.title,
            GeneratedUserStories.snippet,
            GeneratedUserStories.full_text,
            GeneratedUserStories.created_at,
            GeneratedUserStories.updated_at,
            GeneratedUserStories.category,
            GeneratedUserStories.tags,
            GeneratedUserStories.slug,
            Creators.username.label("creator_username"),
            Creators.first_name.label("creator_first_name"),
            Creators.last_name.label("creator_last_name"),
            Editors.first_name.label("editor_first_name"),
            Editors.last_name.label("editor_last_name")
        )
            .join(Creators, onclause=Creators.id == GeneratedUserStories.author_id)
            .join(Editors, onclause=Editors.id == GeneratedUserStories.editor_id, isouter=True)
            .where(GeneratedUserStories.slug == article_slug)
            .limit(1)
    )
    article = result.first()
    if not article:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f'no article found for id {article_slug}'
        )
    return article

@router.get(
    '/creator/{username}',
    response_model=CreatorProfileResponse
)
async def get_creator_profile(
    session: Annotated[AsyncSession, Depends(get_session)],
    username: Annotated[str, Path(
        min_length=2,
        max_length=64,
        regex="^@[A-Za-z0-9._%+-]+$"
    )],
    sort_by: Annotated[str, Query(pattern="^(newest|oldest|popular)$")] = "newest"
):
    result = await session.execute(
        select(Authors)
            .where(Authors.user.has(username=username))
    )
    creator = result.scalars().first()
    
    if not creator:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="creator not found"
        )
    creator_user_db = creator.user
    creator_username = creator_user_db.username
    creator_first_name = creator_user_db.first_name
    creator_last_name = creator_user_db.last_name

    articles_query = (
        select(GeneratedUserStories)
            .options(
                selectinload(
                    GeneratedUserStories.editor
                )
            )
            .where(
                GeneratedUserStories.user_story.has(publish_status=UserStoryPublishStatus.PUBLISHED),
                GeneratedUserStories.author_id == creator.id
            )
    )
    if sort_by == "newest" or sort_by == "popular":
        articles_query = articles_query.order_by(GeneratedUserStories.created_at.desc())
    elif sort_by == "oldest":
        articles_query = articles_query.order_by(GeneratedUserStories.created_at.asc())

    result = await session.execute(articles_query)
    articles = result.scalars().all()

    return CreatorProfileResponse(
        username=creator_username,
        first_name=creator_first_name,
        last_name=creator_last_name,
        bio=creator.bio,
        articles=articles
    )
