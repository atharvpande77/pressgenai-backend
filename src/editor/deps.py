from typing import Annotated, Literal
from fastapi import HTTPException, Path, Depends, status
from src.models import UserStoryPublishStatus
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
import traceback
from uuid import UUID

from src.config.database import get_session
from src.editor.service import get_article_by_id_db
from src.models import Users, UserRoles, GeneratedUserStories
from src.auth.dependencies import role_checker


publish_statuses = [val for val in UserStoryPublishStatus.__members__.values()]

def get_editor_story_status_dep(
    editor_status: Annotated[str, Path(description="Editor story status filter")]
) -> Literal[UserStoryPublishStatus.PENDING, UserStoryPublishStatus.PUBLISHED, UserStoryPublishStatus.WORK_IN_PROGRESS, UserStoryPublishStatus.REJECTED]:
    """Convert status to lowercase and validate."""
    status_lower = editor_status.lower().strip()
    valid_statuses = publish_statuses
    
    if status_lower not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    return status_lower

async def get_article_or_404(article_id: Annotated[UUID, Path(...)], session: Annotated[AsyncSession, Depends(get_session)]):
    try:
        article = await get_article_by_id_db(session, article_id)
        if not article:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no article found for id {article_id}")
        return article
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"error fetching article for id {article_id}")


async def get_verified_article(
    # session: Annotated[AsyncSession, Depends(get_session)],
    article_db: Annotated[GeneratedUserStories, Depends(get_article_or_404)],
    curr_editor: Annotated[Users, Depends(role_checker(UserRoles.EDITOR, UserRoles.ADMIN))]
):
    if article_db.editor_id and article_db.editor_id != curr_editor.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Article already under review by another editor"
        )
    
    # if article_db.user_story.publish_status == UserStoryPublishStatus.PUBLISHED:
    #     raise HTTPException(
    #         status.HTTP_403_FORBIDDEN,
    #         detail="cannot edit a published article"
    #     )
    
    # result = await session.execute(
    #     update(GeneratedUserStories)
    #         .values(editor_id=curr_editor.id)
    #         .where(GeneratedUserStories.id == article_db.id)
    #         .returning(GeneratedUserStories)
    # )
    # updated_article = result.scalars().first()
    # await session.commit()
    # article_db.editor_id = curr_editor.id
    return article_db