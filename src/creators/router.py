from fastapi import APIRouter, Depends, status, UploadFile, Form
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pydantic import EmailStr
from uuid import UUID

from src.config.database import get_session
from src.creators.schemas import (
    AuthorResponseSchema,
    CreatorUpdatePasswordSchema,
    CreatorOnboarding,
    CityResponseSchema
)
from src.creators.service import (
    create_author_db,
    update_creator_password,
    update_creator_profile_db,
    store_creator_onboarding,
    store_creator_links,
    update_onboarding_status
)
from src.models import Users, UserRoles
from src.auth.dependencies import role_checker
from src.creators.utils import get_presigned_s3_url
from src.creators.dependencies import validate_profile_image
from src.aws.client import get_s3_client
from src.aws.utils import get_full_s3_object_url

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
curr_author_dep = Annotated[Users, Depends(role_checker(UserRoles.CREATOR))]

@router.post(
    '/',
    status_code=status.HTTP_201_CREATED,
    response_model=AuthorResponseSchema,
    summary="Register a new creator account",
    description="""Create a new creator account with initial profile information and city registration.
    
    Accepts form data including profile image upload. The profile image is validated for:
    - Allowed types: jpeg, jpg, png, webp, gif, avif
    - Maximum size: 10MB
    
    A unique username is automatically generated from the email address.
    The creator account is created in inactive state and requires admin approval.""",
    responses={
        201: {"description": "Creator account successfully created"},
        400: {"description": "Invalid request data or city ID does not exist"},
        409: {"description": "Creator with this email already exists"},
        500: {"description": "Internal server error while creating account"}
    }
)
async def create_author(
    session: Session,
    s3=Depends(get_s3_client),
    first_name: str = Form(..., max_length=100),
    last_name: Optional[str] = Form(None, max_length=100),
    email: EmailStr = Form(..., max_length=254),
    phone: str | None = Form(None, max_length=20),
    bio: Optional[str] = Form(None, max_length=1500),
    password: str = Form(..., min_length=8, max_length=128, description="Password (8-128 characters)"),
    city_id: UUID = Form(..., description="City ID"),
    profile_image: Optional[UploadFile] = Depends(validate_profile_image)
):
    return await create_author_db(
        session,
        s3,
        first_name,
        email,        # Fixed: email comes before password
        password,     # Fixed: password comes after email
        city_id,
        phone,
        last_name,    # Fixed: correct order
        bio,          # Fixed: correct order
        profile_image # Fixed: correct order
    )
    
    
@router.post(
    '/onboarding',
    status_code=status.HTTP_200_OK,
    summary="Complete creator onboarding process",
    description="""Complete the creator onboarding flow with personal and professional information.
    
    Stores:
    - Personal information (date of birth, education level, work status)
    - City preference for article assignments
    - Optional social media and professional links
    
    Marks the onboarding process as completed for the creator. Can only be called by authenticated creators.""",
    responses={
        200: {"description": "Onboarding completed successfully"},
        401: {"description": "Insufficient permissions - Creator role required"},
        400: {"description": "Invalid request data"},
        500: {"description": "Internal server error while completing onboarding"}
    }
)
async def onboard_creator(
    session: Session,
    curr_creator: curr_author_dep,
    body: CreatorOnboarding
):    
    onboarding_id = await store_creator_onboarding(
        session=session,
        creator_id=curr_creator.id,
        city_id=body.city_id,
        highest_education=body.highest_education,
        highest_educatation_specify=body.education_other_specify,
        work_status=body.work_status,
        work_status_specify=body.work_status_other_specify,
    )

    if body.links:
        await store_creator_links(session, curr_creator.id, body.links)
    
    await update_onboarding_status(session, curr_creator.id, True)
    
    await session.commit()
            
    return {"onboarding_id": onboarding_id}


@router.get(
    '/', 
    response_model=AuthorResponseSchema,
    summary="Retrieve current creator's profile",
    description="""Fetch the complete profile information for the authenticated creator.
    
    Returns all profile data including:
    - Personal information (name, email, phone, username)
    - Profile image URL
    - Biography
    - City and location information
    - Onboarding status
    - Educational and work status
    - Profile update timestamp""",
    responses={
        200: {"description": "Successfully retrieved creator profile"},
        401: {"description": "Insufficient permissions - Creator role required"},
        404: {"description": "Creator profile not found"},
        500: {"description": "Internal server error while fetching profile"}
    }
)
async def get_creator_profile(curr_author: curr_author_dep):
    author_profile = curr_author.author_profile
    return AuthorResponseSchema(
        id=curr_author.id,
        first_name=curr_author.first_name,
        last_name=curr_author.last_name,
        email=curr_author.email,
        phone=curr_author.phone,
        username=curr_author.username,
        bio=getattr(author_profile, 'bio', None),
        date_of_birth=getattr(author_profile, 'date_of_birth', None),
        highest_education=getattr(author_profile, 'highest_education', None),
        highest_education_other_specify=getattr(author_profile, 'highest_education_other_specify', None),
        work_status=getattr(author_profile, 'work_status', None),
        work_status_other_specify=getattr(author_profile, 'work_status_other_specify', None),
        profile_image=get_full_s3_object_url(curr_author.profile_image_key) if curr_author.profile_image_key else None,
        city=CityResponseSchema(
            id=author_profile.city_id,
            name=author_profile.city.name if author_profile.city else None
        ),
        updated_at=getattr(author_profile, 'updated_at', None),
        onboarding_completed=getattr(author_profile, 'onboarding_completed') or False,
    )

@router.patch(
    '/',
    summary="Update creator password",
    description="""Change the password for the authenticated creator.
    
    Requires verification of the current password before allowing the password change.
    The new password must be 8-128 characters and will be hashed before storage.""",
    responses={
        200: {"description": "Password successfully updated"},
        401: {"description": "Incorrect current password or insufficient permissions"},
        400: {"description": "Invalid request data"},
        500: {"description": "Internal server error while updating password"}
    }
)
async def update_password(session: Session, curr_creator: curr_author_dep, body: CreatorUpdatePasswordSchema):
    return await update_creator_password(
        session,
        curr_creator,
        body.old_password,
        body.new_password
    )

@router.put(
    '/',
    response_model=AuthorResponseSchema,
    summary="Update creator profile information",
    description="""Update creator profile details including name, biography, and profile image.
    
    All fields are optional - only provided fields will be updated. Accepts form data with:
    - first_name: Creator's first name (max 100 characters)
    - last_name: Creator's last name (max 100 characters)
    - bio: Biography or professional summary (max 1500 characters)
    - profile_image: Profile photo with validation for file type and size (max 10MB)
    
    Allowed image types: jpeg, jpg, png, webp, gif, avif
    
    Lazy creates Authors record if it doesn't exist when bio is provided.""",
    responses={
        200: {"description": "Profile successfully updated"},
        400: {"description": "Invalid file type or file too large"},
        401: {"description": "Insufficient permissions - Creator role required"},
        500: {"description": "Internal server error while updating profile"}
    }
)
async def update_creator_profile(
    session: Session,
    curr_creator: curr_author_dep,
    s3=Depends(get_s3_client),
    first_name: str | None = Form(None, max_length=100),
    last_name: Optional[str] = Form(None, max_length=100),
    bio: Optional[str] = Form(None, max_length=1500),
    profile_image: Optional[UploadFile] = Depends(validate_profile_image),
):
    return await update_creator_profile_db(
        session,
        s3,
        curr_creator,
        first_name,
        last_name,
        bio,
        profile_image
    )
