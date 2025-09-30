from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy import select
from uuid import UUID

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
    result = await session.execute(
        select(GeneratedUserStories)
        .join(UserStories, onclause=UserStories.id == GeneratedUserStories.user_story_id)
        .where(GeneratedUserStories.category == category, UserStories.publish_status == UserStoryPublishStatus.PUBLISHED)
        .limit(limit)
        .offset(offset)
    )
    articles = result.scalars().all()
    return articles


@router.get('/categories')
async def get_all_categories():
    return [cat.value.title() for cat in NewsCategory]


@router.get('/{article_id}', response_model=ArticleResponse)
async def get_article_by_id(
    session: Annotated[AsyncSession, Depends(get_session)],
    article_id: UUID
):
    
    result = await session.execute(
        select(
            GeneratedUserStories,
            Creators.id.label("creator_id"),
            Creators.first_name.label("creator_first_name"),
            Creators.last_name.label("creator_last_name"),
            Editors.id.label("editor_id"),
            Editors.first_name.label("editor_first_name"),
            Editors.last_name.label("editor_last_name")
        )
            .join(Creators, onclause=Creators.id == GeneratedUserStories.author_id)
            .join(Editors, onclause=Editors.id == GeneratedUserStories.editor_id, isouter=True)
            .where(GeneratedUserStories.id == article_id)
            .limit(1)
    )
    article = result.first()
    if not article:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f'no article found for id {article_id}'
        )
    return article

@router.get('/creator/{creator_id}', response_model=CreatorProfileResponse)
async def get_creator_profile(
    session: Annotated[AsyncSession, Depends(get_session)],
    creator_id: UUID
):
    
    result = await session.execute(
        select(Authors)
            .join(UserStories, onclause=UserStories.author_id == Authors.id)
            .where(Authors.id == creator_id, UserStories.publish_status == UserStoryPublishStatus.PUBLISHED)
    )
    creator = result.scalars().first()

    return CreatorProfileResponse(
        id=creator.id,
        first_name=creator.user.first_name,
        last_name=creator.user.last_name,
        bio=creator.bio,
        articles=creator.generated_user_stories
    )
