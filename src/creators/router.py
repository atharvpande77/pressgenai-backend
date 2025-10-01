from fastapi import APIRouter, Depends, status
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_session
from src.creators.schemas import CreateAuthorSchema, AuthorResponseSchema, CreatorUpdatePasswordSchema, UpdateProfileSchema
from src.creators.service import create_author_db, get_author_profile_db, update_creator_password, update_creator_profile_db
from src.models import Users, UserRoles
from src.auth.dependencies import role_checker

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
curr_author_dep = Annotated[Users, Depends(role_checker(UserRoles.CREATOR))]

@router.post('/', status_code=status.HTTP_201_CREATED, response_model=AuthorResponseSchema)
async def create_author(session: Session, author: CreateAuthorSchema):
    return await create_author_db(session, author)

@router.get('/', response_model=AuthorResponseSchema)
async def get_creator_profile(curr_author: curr_author_dep):
    return AuthorResponseSchema(
        id=curr_author.id,
        first_name=curr_author.first_name,
        last_name=curr_author.last_name,
        email=curr_author.email,
        bio=curr_author.author_profile.bio,
        profile_image="https://fastly.picsum.photos/id/423/110/100.jpg?hmac=D5gzbIo4lyz2RW3hcevcREoogBK39r7XX4NyHFCMgqE"
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
async def update_creator_profile(session: Session, curr_creator: curr_author_dep, body: UpdateProfileSchema):
    return await update_creator_profile_db(
        session,
        curr_creator,
        body
    )