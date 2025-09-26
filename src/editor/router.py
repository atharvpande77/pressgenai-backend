from fastapi import APIRouter, Depends
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_session
from src.editor.service import get_articles_by_publish_status, update_article_db, publish_article_db, reject_article_db
from src.editor.deps import get_editor_story_status_dep, get_article_or_404
from src.editor.schemas import ArticleItem, EditArticleSchema, RejectArticleSchema, RejectedEndpointResponse
from src.models import GeneratedUserStories

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
GetArticleDep = Annotated[GeneratedUserStories, Depends(get_article_or_404)]

@router.get('/articles/status/{editor_status}', response_model=list[ArticleItem])
async def get_articles_editor_dashboard(session: Session, editor_status: Annotated[str, Depends(get_editor_story_status_dep)], limit: int | None = 10, offset: int | None = 0):
    print(editor_status)
    return await get_articles_by_publish_status(session, editor_status, limit, offset)

@router.get('/articles/{article_id}', response_model=ArticleItem)
async def fetch_article_by_id(article_db: GetArticleDep):
    return article_db

@router.patch('/articles/{article_id}')
async def edit_article(session: Session, article_id: str, payload: EditArticleSchema):
    return await update_article_db(session, article_id, payload)

@router.post('/articles/{article_id}')
async def publish_article(session: Session, article_db: GetArticleDep):
    """
        For now, only changes the publish status to published 
    """

    return await publish_article_db(session, article_db)

@router.post('/articles/{article_id}/reject', response_model=RejectedEndpointResponse)
async def reject_article(session: Session, payload: RejectArticleSchema, article_db: GetArticleDep):
    """
        For now, only changes the publish status to rejected
    """
    return await reject_article_db(session, article_db, payload.reason)

