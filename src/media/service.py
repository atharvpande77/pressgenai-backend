from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Annotated
from fastapi import Path, HTTPException, status, Depends

from src.models import GeneratedUserStories, UserRoles, Users, UserStoryStatus
from src.auth.dependencies import get_current_user
from src.config.database import get_session

# async def check_generated_article_exists(
#     session: AsyncSession,
#     generated_article_id: UUID
# ) -> bool:
#     article_exists = await session.scalar(
#         select(GeneratedUserStories).where(id==generated_article_id)
#     )
#     return article_exists is None


async def get_generated_article_dep(
    session: Annotated[AsyncSession, Depends(get_session)],
    generated_article_id: Annotated[UUID, Path(...)]
):
    article = await session.get(GeneratedUserStories, generated_article_id)
    if not article:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"no article found for id {generated_article_id}"
        )
    return article


async def check_article_authorization(
    curr_user: Annotated[Users, Depends(get_current_user)],
    article: Annotated[GeneratedUserStories, Depends(get_generated_article_dep)]
):
    role = curr_user.role
    if role == UserRoles.CREATOR:
        if article.author_id != curr_user.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="cannot edit other creator's article"
            )
        if article.user_story.status == UserStoryStatus.SUBMITTED:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"article with id {article.id} is already submitted"
            )
        
    elif role == UserRoles.EDITOR:
        if article.editor_id not in [None, curr_user.id]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="article already under review by other editor"
            )
        
    return article