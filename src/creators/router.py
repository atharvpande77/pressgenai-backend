from fastapi import APIRouter, Depends, status, HTTPException, UploadFile, File, Form
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pydantic import EmailStr

from src.config.database import get_session
from src.creators.schemas import CreateAuthorSchema, AuthorResponseSchema, CreatorUpdatePasswordSchema, UpdateProfileSchema
from src.creators.service import create_author_db, update_creator_password, update_creator_profile_db
from src.models import Users, UserRoles
from src.auth.dependencies import role_checker
from src.creators.utils import get_presigned_s3_url
from src.creators.dependencies import validate_profile_image
from src.aws.client import get_s3_client
from src.aws.utils import get_full_s3_object_url

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
curr_author_dep = Annotated[Users, Depends(role_checker(UserRoles.CREATOR))]

@router.post('/', status_code=status.HTTP_201_CREATED, response_model=AuthorResponseSchema)
async def create_author(
    session: Session,
    s3=Depends(get_s3_client),
    first_name: str = Form(..., max_length=100),
    last_name: Optional[str] = Form(None, max_length=100),
    email: EmailStr = Form(..., max_length=254),
    phone: str | None = Form(None, max_length=20),
    bio: Optional[str] = Form(None, max_length=1500),
    password: str = Form(..., min_length=8, max_length=128, description="Password (8-128 characters)"),
    profile_image: Optional[UploadFile] = Depends(validate_profile_image)
):
    return await create_author_db(
        session,
        s3,
        first_name,
        email,        # Fixed: email comes before password
        password,     # Fixed: password comes after email
        phone,
        last_name,    # Fixed: correct order
        bio,          # Fixed: correct order
        profile_image # Fixed: correct order
    )


@router.get('/', response_model=AuthorResponseSchema)
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
        profile_image=get_full_s3_object_url(curr_author.profile_image_key) if curr_author.profile_image_key else None
    )

@router.patch('/')
async def update_password(session: Session, curr_creator: curr_author_dep, body: CreatorUpdatePasswordSchema):
    return await update_creator_password(
        session,
        curr_creator,
        body.old_password,
        body.new_password
    )

@router.put('/', response_model=AuthorResponseSchema)
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