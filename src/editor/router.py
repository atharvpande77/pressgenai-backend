from fastapi import APIRouter, Depends, status, HTTPException
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.config.database import get_session
from src.editor.service import get_articles_by_publish_status, edit_article_db, publish_article_db, reject_article_db, get_all_creators_db, approve_or_reject_creator_db, reset_creator_password_db, get_creator_by_id, add_creator_db
from src.editor.deps import get_editor_story_status_dep, get_article_or_404, get_verified_article
from src.editor.schemas import ArticleItem, EditArticleSchema, RejectArticleSchema, RejectedEndpointResponse, ArticleFullItem, UpdateCreatorPassword, CreatorItem, CreateCreatorSchema
from src.models import GeneratedUserStories, Users, UserRoles
from src.auth.dependencies import role_checker
from src.auth.utils import verify_pw
from src.aws.utils import get_full_s3_object_url, get_images_with_urls
from src.schemas import GeneratedStoryResponseSchema


router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
GetArticleDep = Annotated[GeneratedUserStories, Depends(get_article_or_404)]
EditorRoleDep = Annotated[Users, Depends(role_checker(UserRoles.EDITOR, UserRoles.ADMIN))]
VerifyArticleDep = Annotated[Users, Depends(get_verified_article)]

@router.get('/articles/status/{editor_status}', response_model=list[ArticleItem])
async def get_articles_editor_dashboard(session: Session, curr_editor: EditorRoleDep, editor_status: Annotated[str, Depends(get_editor_story_status_dep)], limit: int | None = 10, offset: int | None = 0):
    return await get_articles_by_publish_status(session, editor_status, curr_editor.id, limit, offset)

@router.get('/articles/{article_id}')
async def fetch_article_by_id(article_db: GetArticleDep, curr_editor: EditorRoleDep):
    article_db_dict = article_db.__dict__
    creator = article_db.author.user
    editor=getattr(article_db.editor, 'user', None)
    images_keys = article_db_dict.get('images_keys', [])
    article_db_dict['images'] = get_images_with_urls(images_keys)
    
    # editor can only edit/publish articles under their review or if no editor assigned
    can_edit = curr_editor.id == article_db.editor_id or article_db.editor_id is None

    return ArticleFullItem(
        **article_db_dict,
        creator_username = creator.username,
        creator_first_name = creator.first_name,
        creator_last_name = creator.last_name,
        creator_profile_image=get_full_s3_object_url(creator.profile_image_key),
        editor_username = editor.username if editor else None,
        editor_first_name = editor.first_name if editor else None,
        editor_last_name = editor.last_name if editor else None,
        editor_profile_image=get_full_s3_object_url(editor.profile_image_key) if editor else None,
        can_edit=can_edit
    )

@router.patch('/articles/{article_id}', response_model=GeneratedStoryResponseSchema)
async def edit_article(session: Session, article: VerifyArticleDep, curr_editor: EditorRoleDep, payload: EditArticleSchema):
    return await edit_article_db(session, article, payload, curr_editor.id)

@router.post('/articles/{article_id}')
async def publish_article(session: Session, article: VerifyArticleDep, curr_editor: EditorRoleDep):
    """
        For now, only changes the publish status to published 
    """
    return await publish_article_db(session, article, curr_editor.id)

@router.post('/articles/{article_id}/reject', response_model=RejectedEndpointResponse)
async def reject_article(session: Session, payload: RejectArticleSchema, curr_editor: EditorRoleDep, article_db: GetArticleDep):
    """
        For now, only changes the publish status to rejected
    """
    return await reject_article_db(session, article_db, payload.reason, curr_editor.id)


# Creator management
@router.get('/creators', response_model=list[CreatorItem])
async def get_all_creators(session: Annotated[AsyncSession, Depends(get_session)], curr_editor: EditorRoleDep, limit: int = 20, offset: int = 0):
    return await get_all_creators_db(
        session, limit, offset
    )
    
@router.get('/creators/{creator_id}')
async def get_creator(session: Annotated[AsyncSession, Depends(get_session)], curr_editor: EditorRoleDep, creator_id: UUID):
    return await get_creator_by_id(session, creator_id)

@router.post('/creators')
async def create_new_creator(session: Annotated[AsyncSession, Depends(get_session)], curr_editor: EditorRoleDep, payload: CreateCreatorSchema):
    return await add_creator_db(session, curr_editor.id, payload)
    
@router.patch('/creators/{creator_id}/approve', response_model=CreatorItem)
async def approve_creator(session: Annotated[AsyncSession, Depends(get_session)], curr_editor: EditorRoleDep, creator_id: UUID, approve: bool):
    return await approve_or_reject_creator_db(
        session, curr_editor.id, creator_id, approve
    )
    
@router.patch('/creators/{creator_id}/password')
async def reset_creator_password(session: Annotated[AsyncSession, Depends(get_session)], curr_editor: EditorRoleDep, creator_id: UUID, payload: UpdateCreatorPassword):
    if not verify_pw(payload.editor_password, curr_editor.password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="incorrect password for editor"
        )
    return await reset_creator_password_db(
        session, creator_id, payload.new_password
    )
    
