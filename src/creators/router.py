from fastapi import (
    APIRouter,
    Depends,
    status,
    UploadFile,
    Form,
    HTTPException
)
from typing import Annotated
from typing import Optional
from pydantic import EmailStr
from uuid import UUID
from src.config.database import Session
from src.creators.schemas import (
    AuthorResponseSchema,
    CreatorUpdatePasswordSchema,
    CreatorOnboarding,
    CreatorOnboardingStatus
)
from src.creators.service import (
    create_author_db,
    update_creator_password,
    update_creator_profile_db,
    persist_creator_onboarding,
    fetch_creator_onboarding_status,
)
from src.models import Users, UserRoles
from src.auth.dependencies import role_checker
from src.creators.dependencies import validate_profile_image
from src.aws.client import get_s3_client

router = APIRouter()

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
    
    
@router.get(
    '/onboarding',
    response_model=CreatorOnboardingStatus,
    summary="Retrieve creator onboarding details",
    description="""Return the authenticated creator's stored onboarding information, including personal details, city preference, and any saved profile links.
    
    Returns:
    - Date of birth, education, and work status
    - Preferred city identifier and name
    - Saved creator links (social, portfolio, etc.)
    """,
    responses={
        200: {"description": "Successfully returned onboarding details (personal info, city, links)"},
        401: {"description": "Insufficient permissions - Creator role required"},
        404: {"description": "Creator profile not found"},
        500: {"description": "Internal server error while fetching profile"}
    }
)
async def get_existing_creator_onboarding(
    session: Session,
    curr_creator: curr_author_dep,
):
    onboarding_status = await fetch_creator_onboarding_status(session, curr_creator.id)
    if not onboarding_status:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found"
        )

    return onboarding_status
    
    
@router.post(
    '/onboarding',
    status_code=status.HTTP_200_OK,
    response_model=CreatorOnboardingStatus,
    summary="Upsert creator onboarding details",
    description="""Stores or updates onboarding fields (DOB, education, work status, city choice, links) for the authenticated creator.

    The endpoint upserts provided values, deletes the previous links if any, and returns the full onboarding snapshot (same response as GET /onboarding).""",
    responses={
        200: {"description": "Returns the creator's onboarding snapshot (DOB, education, work status, city, links)"},
        400: {"description": "Invalid payload or city_id does not exist"},
        401: {"description": "Insufficient permissions - Creator role required"},
        404: {"description": "Creator profile not found"},
        500: {"description": "Internal server error while persisting onboarding data"}
    }
)
async def onboard_creator(
    session: Session,
    curr_creator: curr_author_dep,
    body: CreatorOnboarding
):
    curr_creator_profile = curr_creator.author_profile
    if not curr_creator_profile:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found"
        )

    onboarding_status = await persist_creator_onboarding(
        session=session,
        creator_id=curr_creator.id,
        payload=body,
    )

    if not onboarding_status:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load onboarding status"
        )

    await session.commit()
    return onboarding_status


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
    author_city = author_profile.city if author_profile else None
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
        profile_image_key=curr_author.profile_image_key,
        city=author_profile.city.name if author_city else None,
        city_id=author_profile.city.id if author_city else None,
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
