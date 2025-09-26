from typing import Annotated, Literal
from fastapi import HTTPException, Path, Depends, status
from src.models import UserStoryPublishStatus
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_session
from src.editor.service import get_article_by_id_db

def get_editor_story_status_dep(
    editor_status: Annotated[str, Path(description="Editor story status filter")]
) -> Literal[UserStoryPublishStatus.PENDING, UserStoryPublishStatus.PUBLISHED, UserStoryPublishStatus.REJECTED]:
    """Convert status to lowercase and validate."""
    status_lower = editor_status.lower().strip()
    valid_statuses = [UserStoryPublishStatus.PENDING, UserStoryPublishStatus.PUBLISHED, UserStoryPublishStatus.REJECTED]
    
    if status_lower not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    return status_lower

async def get_article_or_404(article_id: Annotated[str, Path(...)], session: Annotated[AsyncSession, Depends(get_session)]):
    try:
        article = await get_article_by_id_db(session, article_id)
        if not article:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no article found for id {article_id}")
        return article
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"error fetching article for id {article_id}")