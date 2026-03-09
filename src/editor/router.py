from fastapi import APIRouter, Depends, status, HTTPException
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.config.database import get_session
from src.editor.service import get_articles_by_publish_status, edit_article_db, publish_article_db, reject_article_db, get_all_creators_db, approve_or_reject_creator_db, reset_creator_password_db, get_creator_by_id, add_creator_db, get_article_by_id_db
from src.editor.deps import get_editor_story_status_dep, get_article_or_404, get_verified_article
from src.editor.schemas import ArticleItem, EditArticleSchema, RejectArticleSchema, RejectedEndpointResponse, ArticleFullResponse, UpdateCreatorPassword, CreatorItem, CreateCreatorSchema
from src.models import GeneratedUserStories, Users, UserRoles
from src.auth.dependencies import role_checker
from src.auth.utils import verify_pw
from src.aws.utils import get_full_s3_object_url, get_images_with_urls
from src.schemas import GeneratedStoryResponseSchema
from src.config.database import Session


router = APIRouter()

GetArticleDep = Annotated[GeneratedUserStories, Depends(get_article_or_404)]
EditorRoleDep = Annotated[Users, Depends(role_checker(UserRoles.EDITOR, UserRoles.ADMIN))]
VerifyArticleDep = Annotated[Users, Depends(get_verified_article)]

@router.get(
    '/articles/status/{editor_status}',
    response_model=list[ArticleItem],
    summary="Fetch articles by publish status for editor dashboard",
    description="""Retrieve a paginated list of articles filtered by their publish status.
    
    The editor can only see articles that are assigned to them or unassigned.
    Articles must be in SUBMITTED status to appear. Results are filtered by the editor's assigned cities and categories.
    
    Valid statuses are: pending, published, work_in_progress, rejected""",
    responses={
        200: {"description": "Successfully retrieved articles list"},
        400: {"description": "Invalid status parameter"},
        403: {"description": "Insufficient permissions - Editor or Admin role required"},
        500: {"description": "Internal server error while fetching articles"}
    }
)
async def get_articles_editor_dashboard(
    session: Session,
    curr_editor: EditorRoleDep,
    editor_status: Annotated[str, Depends(get_editor_story_status_dep)],
    limit: int | None = 10,
    offset: int | None = 0
):
    articles = await get_articles_by_publish_status(session, editor_status, curr_editor.id, limit, offset)
    return articles

@router.get(
    '/articles/{article_id}',
    response_model=ArticleFullResponse,
    summary="Fetch complete article details by article ID",
    description="""Retrieve detailed information about a specific generated article.
    
    Returns the complete article data including:
    - Article content (title, snippet, full_text)
    - Creator and editor information
    - Associated categories and city
    - Publication status and timestamps
    - Edit permissions based on current editor assignment""",
    responses={
        200: {"description": "Successfully retrieved article details"},
        404: {"description": "Article not found"},
        403: {"description": "Insufficient permissions - Editor or Admin role required"},
        500: {"description": "Internal server error while fetching article"}
    }
)
async def fetch_article_by_id(
    session: Session,
    curr_editor: EditorRoleDep,
    article: GetArticleDep,
): 
    user_story = article.user_story
    article_editor_id = article.editor_id
    can_edit = (curr_editor.id == article_editor_id or article_editor_id is None)
    categories = article.categories
    article_city = article.city
    
    creator = article.author.user
    editor = getattr(article, 'editor')
    
    return ArticleFullResponse.model_validate({
        **article.__dict__,
        "creator": creator,
        "editor": editor or {"id": None, "first_name": None, "last_name": None, "username": None, "profile_image_key": None},
        "categories": categories,
        "city": article_city,
        "can_edit": can_edit,
        "publish_status": user_story.publish_status,
        "submitted_at": user_story.submitted_at,
        "city": article_city.name,
    })
        
    
from src.editor.service import validate_categories, get_city_by_id, set_publish_status
from src.models import UserStoryPublishStatus
    
@router.patch(
    '/articles/{article_id}',
    response_model=GeneratedStoryResponseSchema,
    summary="Edit article content and metadata",
    description="""Update article details including title, content, tags, images, categories, and location scope.
    
    Only fields provided in the request body will be updated. The article must be assigned to the current editor or unassigned.
    Updating an article with PENDING status automatically changes its status to WORK_IN_PROGRESS.
    
    Editable fields:
    - title: Article headline
    - snippet: Short summary
    - full_text: Complete article content
    - tags: Array of article tags
    - images_keys: S3 image keys for article media
    - categories: Array of category IDs (validated against available categories)
    - location_scope: Geographic scope of the article
    - city: City ID for the article location""",
    responses={
        200: {"description": "Article successfully updated"},
        400: {"description": "Invalid request data or empty update payload"},
        403: {"description": "Article assigned to another editor or insufficient permissions"},
        404: {"description": "Article or referenced city/categories not found"},
        500: {"description": "Internal server error while updating article"}
    }
)
async def edit_article(
    session: Session,
    article: VerifyArticleDep,
    curr_editor: EditorRoleDep,
    payload: EditArticleSchema
):
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="all fields cannot be empty"
        )
        
    article_id = article.id
    curr_editor_id = curr_editor.id
    
    update_fields = {
        k: v for k, v in values.items() if k in ['title', 'snippet', 'full_text', 'tags', 'images_keys', 'categories', 'location_scope', 'city']
    }
    categories = update_fields.get('categories')
    
    if categories:
        validated_category_ids = await validate_categories(
            session,
            category_ids=categories
        )
        if not validated_category_ids:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="invalid category id"
            )
            
        update_fields['categories'] = validated_category_ids
        
    city_id = update_fields.get('city')
    if city_id:
        valid_city_id = await get_city_by_id(
            session,
            city_id
        )
        if not valid_city_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="invalid city id"
            )
        update_fields['city_id'] = city_id
    
    # print(f"Article update fields:\n{update_fields}")
    
    updated_article = await edit_article_db(
        session,
        article_id=article.id,
        values=update_fields
    )
            
    user_story = article.user_story
    publish_status = getattr(user_story, 'publish_status')
    
    if publish_status == UserStoryPublishStatus.PENDING:
        await set_publish_status(
            session,
            user_story_id=article.user_story_id,
            article_id=article_id,
            new_publish_status=UserStoryPublishStatus.WORK_IN_PROGRESS,
            curr_editor_id=curr_editor_id
        )
        
    await session.commit()
    return updated_article

from src.models import LocationScope

@router.post(
    '/articles/{article_id}',
    summary="Publish an article with metadata validation",
    description="""Publish an article and update its status to PUBLISHED after validating all required metadata.
    
    Before publishing, validates that the article has:
    - A reviewed location scope (not UNREVIEWED)
    - An assigned city
    - A non-empty title
    - Full article text content
    
    Once validated, sets the publish status to PUBLISHED, records the publication timestamp,
    and assigns the article to the current editor.""",
    responses={
        200: {"description": "Article successfully published"},
        403: {"description": "Article assigned to another editor or insufficient permissions"},
        404: {"description": "Article or associated story not found"},
        409: {"description": "Conflict - article is already published"},
        422: {"description": "Unprocessable entity - article missing required metadata (location_scope, city, title, or full_text)"},
        500: {"description": "Internal server error while publishing article"}
    }
)
async def publish_article(
    session: Session,
    article: VerifyArticleDep,
    curr_editor: EditorRoleDep
):
    user_story = article.user_story
    publish_status = user_story.publish_status
    
    if publish_status == UserStoryPublishStatus.PUBLISHED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Cannot publish an article that is already published"
        )
        
    if (article.location_scope == LocationScope.UNREVIEWED) or (article.city_id is None) or (not article.title) or (not article.full_text):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot publish an article with missing or incomplete metadata"
        )
    
    await set_publish_status(
        session,
        user_story_id=article.user_story_id,
        article_id=article.id,
        new_publish_status=UserStoryPublishStatus.PUBLISHED,
        curr_editor_id=curr_editor.id
    )
    
    await session.commit()
    
    return {"message": "success"}
    

@router.post(
    '/articles/{article_id}/reject',
    response_model=RejectedEndpointResponse,
    summary="Reject an article with a reason",
    description="""Reject a submitted article and set its status to REJECTED.
    
    Records the rejection reason in the database for creator feedback.
    Updates the editor_id to the current editor.
    The rejection reason must be provided in the request body.""",
    responses={
        200: {"description": "Article successfully rejected with reason recorded"},
        400: {"description": "Missing or invalid rejection reason"},
        403: {"description": "Insufficient permissions - Editor or Admin role required"},
        404: {"description": "Article or associated story not found"},
        500: {"description": "Internal server error while rejecting article"}
    }
)
async def reject_article(
    session: Session,
    payload: RejectArticleSchema,
    curr_editor: EditorRoleDep,
    article_db: GetArticleDep
):
    params = {}
    if payload.reason:
        params["rejection_reason"] = payload.reason
    
    user_story = article_db.user_story
    publish_status = user_story.publish_status
    
    if publish_status == UserStoryPublishStatus.REJECTED or publish_status == UserStoryPublishStatus.PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Cannot reject an article that is already rejected or is pending"
        )
        
    await set_publish_status(
        session,
        user_story_id=article_db.user_story_id,
        article_id=article_db.id,
        new_publish_status=UserStoryPublishStatus.REJECTED,
        curr_editor_id=curr_editor.id,
        params=params or None
    )
    
    await session.commit()
    
    # return await reject_article_db(session, article_db, payload.reason, curr_editor.id)
    return {"message": "success"}


# Creator management
@router.get(
    '/creators',
    response_model=list[CreatorItem],
    summary="Retrieve all creators with pagination",
    description="""Fetch a paginated list of all creators (users with CREATOR role).
    
    Returns creator details including:
    - Basic profile information (name, email, username)
    - Active status and approval status
    - Creator biography
    - Profile image URL
    - Count of published articles""",
    responses={
        200: {"description": "Successfully retrieved creators list"},
        403: {"description": "Insufficient permissions - Editor or Admin role required"},
        500: {"description": "Internal server error while fetching creators"}
    }
)
async def get_all_creators(session: Annotated[AsyncSession, Depends(get_session)], curr_editor: EditorRoleDep, limit: int = 20, offset: int = 0):
    return await get_all_creators_db(
        session, limit, offset
    )
    
@router.get(
    '/creators/{creator_id}',
    response_model=CreatorItem,
    summary="Fetch creator details by ID",
    description="""Retrieve detailed information about a specific creator.
    
    Returns:
    - Creator profile information
    - Active status and approval details
    - Biography and profile image
    - Number of published articles""",
    responses={
        200: {"description": "Successfully retrieved creator details"},
        403: {"description": "Insufficient permissions - Editor or Admin role required"},
        404: {"description": "Creator not found"},
        500: {"description": "Internal server error while fetching creator"}
    }
)
async def get_creator(session: Annotated[AsyncSession, Depends(get_session)], curr_editor: EditorRoleDep, creator_id: UUID):
    return await get_creator_by_id(session, creator_id)

@router.post(
    '/creators',
    response_model=CreatorItem,
    summary="Create a new creator account",
    description="""Create a new creator account with initial credentials.
    
    The endpoint generates a unique username from the provided email.
    If the active flag is set to true, the creator is automatically approved by the current editor.
    
    Required fields in request body:
    - first_name: Creator's first name
    - last_name: Creator's last name
    - email: Unique email address
    - password: Initial password (will be hashed)
    - active: Boolean flag to auto-approve the creator""",
    responses={
        201: {"description": "Creator successfully created"},
        400: {"description": "Invalid request data"},
        403: {"description": "Insufficient permissions - Editor or Admin role required"},
        409: {"description": "Email already exists - creator with this email already registered"},
        500: {"description": "Internal server error while creating creator"}
    }
)
async def create_new_creator(session: Annotated[AsyncSession, Depends(get_session)], curr_editor: EditorRoleDep, payload: CreateCreatorSchema):
    return await add_creator_db(session, curr_editor.id, payload)
    
@router.patch(
    '/creators/{creator_id}/approve',
    response_model=CreatorItem,
    summary="Approve or reject a creator account",
    description="""Update the active status of a creator account.
    
    Use approve=true to activate/approve a creator account.
    Use approve=false to deactivate/reject a creator account.
    
    Records the approving editor (approved_by) and approval timestamp.
    Query parameter:
    - approve: Boolean flag (true to approve, false to reject)""",
    responses={
        200: {"description": "Creator status successfully updated"},
        403: {"description": "Insufficient permissions - Editor or Admin role required"},
        404: {"description": "Creator not found"},
        500: {"description": "Internal server error while updating creator status"}
    }
)
async def approve_creator(session: Annotated[AsyncSession, Depends(get_session)], curr_editor: EditorRoleDep, creator_id: UUID, approve: bool):
    return await approve_or_reject_creator_db(
        session, curr_editor.id, creator_id, approve
    )
    
@router.patch(
    '/creators/{creator_id}/password',
    summary="Reset creator's password",
    description="""Reset a creator's password by providing the current editor's password for verification.
    
    For security, the endpoint requires the current editor to authenticate with their own password.
    
    Request body fields:
    - new_password: The new password for the creator
    - editor_password: The current editor's password (for verification)""",
    responses={
        200: {"description": "Creator password successfully reset"},
        400: {"description": "Invalid request data"},
        401: {"description": "Editor password verification failed"},
        403: {"description": "Insufficient permissions - Editor or Admin role required"},
        404: {"description": "Creator not found"},
        500: {"description": "Internal server error while resetting password"}
    }
)
async def reset_creator_password(session: Annotated[AsyncSession, Depends(get_session)], curr_editor: EditorRoleDep, creator_id: UUID, payload: UpdateCreatorPassword):
    if not verify_pw(payload.editor_password, curr_editor.password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="incorrect password for editor"
        )
    return await reset_creator_password_db(
        session, creator_id, payload.new_password
    )
    
