from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.exc import IntegrityError
from typing import Annotated
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from uuid import UUID

from src.auth.dependencies import role_checker
from src.config.database import Session
from src.models import Users, UserRoles, GeneratedUserStories, UserStories, UserStoryPublishStatus, Authors, Cities, Categories, UserLinks
from src.admin.schemas import NewInvite, NewUserSchema, AdminCreateUserResponse, AdminPublishedArticleItem, UpdateArticleStatusSchema
from src.creators.utils import hash_password
from src.admin.service import store_user, store_editor_cities_and_categories

router = APIRouter()

admin_role_dep = Annotated[Users, Depends(role_checker(UserRoles.ADMIN))]


@router.post(
    '/',
    response_model=AdminCreateUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new user",
    description="Create a new user (creator or editor) with specified roles and permissions. Creators require a city; editors require cities and optionally categories.",
    responses={
        201: {"description": "User created successfully"},
        400: {"description": "Invalid city ID, category ID, or request data"},
        409: {"description": "User already exists"},
    }
)
async def add_new_user(
    session: Session,
    curr_admin: admin_role_dep,
    new_user: NewUserSchema
):
    hashed_password = hash_password(new_user.password)
    role = new_user.role
    
    try:
        user = await store_user(
            session=session,
            admin_id=curr_admin.id,
            email=new_user.email,
            password=hashed_password,
            first_name=new_user.first_name,
            role=role,
            last_name=new_user.last_name,
            phone=new_user.phone_number,
        )
    except IntegrityError as exc:
        await session.rollback()
        if getattr(exc, "orig", None) and getattr(exc.orig, "pgcode", None) == "23505":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="user already exists"
            ) from exc
        raise
    user_id = user.id

    if role == UserRoles.CREATOR:
        city_id = new_user.city_ids[0]
        city_exists = await session.get(Cities, city_id)
        if not city_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid city id"
            )

        await session.execute(
            insert(Authors).values(
                id=user_id,
                bio=new_user.bio,
                date_of_birth=new_user.date_of_birth,
                highest_education=new_user.highest_education,
                highest_education_other_specify=new_user.education_other_specify,
                work_status=new_user.work_status,
                work_status_other_specify=new_user.work_status_other_specify,
                city_id=city_id,
                onboarding_completed=True,
            )
        )
        if new_user.links:
            await session.execute(
                insert(UserLinks),
                [
                    {
                        "user_id": user_id,
                        "link_type": link.link_type,
                        "platform": link.platform,
                        "url": str(link.url),
                        "description": link.description,
                    }
                    for link in new_user.links
                ],
            )
    elif role == UserRoles.EDITOR:            
        for city_id in new_user.city_ids:
            if not await session.get(Cities, city_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"invalid city id: {city_id}"
                )
        if new_user.category_ids:
            for category_id in new_user.category_ids:
                if not await session.get(Categories, category_id):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"invalid category id: {category_id}"
                    )
        await store_editor_cities_and_categories(
            session=session,
            editor_id=user_id,
            city_ids=new_user.city_ids,
            category_ids=new_user.category_ids or []
        )

    await session.commit()
    await session.refresh(user)

    return AdminCreateUserResponse.model_validate(user)


# Add invite features later.

# @router.post('/invites')
# async def invite_user(
#     session: Session,
#     curr_admin: admin_role_dep,
#     new_invite: NewInvite
# ):
#     ...
    
    
# @router.post('/invites/accept')
# async def accept_invite(
#     session: Session,
#     invite_token: str
# ):
#     ...


@router.get(
    '/articles/published',
    response_model=list[AdminPublishedArticleItem],
    summary="Get all published articles",
    description="Retrieve a paginated list of all published and rejected articles with full details including authors, editors, and categories.",
    responses={
        200: {"description": "List of published articles retrieved successfully"},
    }
)
async def get_all_published_articles(
    session: Session,
    curr_admin: admin_role_dep,
    limit: int = 20,
    offset: int = 0,
):
    result = await session.execute(
        select(GeneratedUserStories)
        .join(UserStories, GeneratedUserStories.user_story_id == UserStories.id)
        .where(
            UserStories.publish_status.in_(
                [UserStoryPublishStatus.PUBLISHED, UserStoryPublishStatus.REJECTED]
            )
        )
        .options(
            selectinload(GeneratedUserStories.categories),
            selectinload(GeneratedUserStories.author).selectinload(Authors.user),
            selectinload(GeneratedUserStories.editor),
            selectinload(GeneratedUserStories.user_story),
        )
        .order_by(GeneratedUserStories.published_at.desc(), GeneratedUserStories.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().unique().all()


@router.patch(
    "/articles/{article_id}/status",
    summary="Update article publish status",
    description="Update UserStories.publish_status for the given generated article. Allowed values: published, rejected.",
    responses={
        200: {"description": "Article status updated successfully"},
        404: {"description": "Article or user story not found"},
    }
)
async def update_article_status(
    article_id: UUID,
    body: UpdateArticleStatusSchema,
    session: Session,
    curr_admin: admin_role_dep,
):
    result = await session.execute(
        select(GeneratedUserStories.user_story_id)
        .where(GeneratedUserStories.id == article_id)
        .limit(1)
    )
    user_story_id = result.scalar_one_or_none()
    if not user_story_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="article not found",
        )

    update_result = await session.execute(
        update(UserStories)
        .where(UserStories.id == user_story_id)
        .values(publish_status=body.publish_status)
    )
    if update_result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user story not found for article",
        )

    await session.commit()
    return {
        "article_id": article_id,
        "user_story_id": user_story_id,
        "publish_status": body.publish_status,
        "message": "status updated",
    }


@router.patch(
    "/creators/{creator_id}/approval",
    summary="Approve or unapprove creator",
    description="Set Users.active = true/false for a creator user to enable or disable their account.",
    responses={
        200: {"description": "Creator approval status updated successfully"},
        404: {"description": "Creator not found"},
        400: {"description": "User is not a creator"},
    }
)
async def approve_or_unapprove_creator(
    creator_id: UUID,
    approve: bool,
    session: Session,
    curr_admin: admin_role_dep,
):
    creator = await session.get(Users, creator_id)
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="creator not found",
        )
    if creator.role != UserRoles.CREATOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user is not a creator",
        )

    await session.execute(
        update(Users)
        .where(Users.id == creator_id, Users.role == UserRoles.CREATOR)
        .values(active=approve)
    )
    await session.commit()

    return {
        "creator_id": creator_id,
        "active": approve,
        "message": "creator approved" if approve else "creator unapproved",
    }
