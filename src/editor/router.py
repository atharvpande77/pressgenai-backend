from fastapi import APIRouter, Depends
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_session
from src.editor.service import get_articles_by_publish_status, update_article_db, publish_article_db, reject_article_db
from src.editor.deps import get_editor_story_status_dep, get_article_or_404, get_article_and_assign_editor
from src.editor.schemas import ArticleItem, EditArticleSchema, RejectArticleSchema, RejectedEndpointResponse
from src.models import GeneratedUserStories, Users, UserRoles
from src.auth.dependencies import role_checker

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
GetArticleDep = Annotated[GeneratedUserStories, Depends(get_article_or_404)]
EditorRoleDep = Annotated[Users, Depends(role_checker(UserRoles.EDITOR, UserRoles.ADMIN))]
AssignEditorDep = Annotated[Users, Depends(get_article_and_assign_editor)]

@router.get('/articles/status/{editor_status}', response_model=list[ArticleItem])
async def get_articles_editor_dashboard(session: Session, curr_editor: EditorRoleDep, editor_status: Annotated[str, Depends(get_editor_story_status_dep)], limit: int | None = 10, offset: int | None = 0):
    return await get_articles_by_publish_status(session, editor_status, curr_editor.id, limit, offset)

@router.get('/articles/{article_id}')
async def fetch_article_by_id(article_db: GetArticleDep, curr_editor: EditorRoleDep):
    article_db_dict = article_db.__dict__
    creator = article_db.author.user
    return ArticleItem(
        **article_db_dict,
        creator_username = creator.username,
        creator_first_name = creator.first_name,
        creator_last_name = creator.last_name
    )

@router.patch('/articles/{article_id}')
async def edit_article_and_publish(session: Session, assigned_article: AssignEditorDep, article_id: str, payload: EditArticleSchema):
    return await update_article_db(session, article_id, payload, assigned_article.editor_id)

@router.post('/articles/{article_id}')
async def publish_article(session: Session, article_db: GetArticleDep, assigned_article: AssignEditorDep):
    """
        For now, only changes the publish status to published 
    """

    return await publish_article_db(session, article_db, assigned_article.editor_id)

@router.post('/articles/{article_id}/reject', response_model=RejectedEndpointResponse)
async def reject_article(session: Session, payload: RejectArticleSchema, curr_editor: EditorRoleDep, article_db: GetArticleDep):
    """
        For now, only changes the publish status to rejected
    """
    return await reject_article_db(session, article_db, payload.reason, curr_editor.id)

