from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, DatabaseError
from sqlalchemy import select, update
from fastapi import HTTPException, status
import secrets

from src.creators.schemas import CreateAuthorSchema, AuthorResponseSchema, UpdateProfileSchema
from src.models import Authors, Users, UserRoles
from src.creators.utils import hash_password
from src.auth.utils import verify_pw


async def _check_username_exists(session: AsyncSession, username: str) -> bool:
    existing_user = await session.scalar(
        select(Users).where(Users.username == username)
    )
    return existing_user is not None

async def generate_unique_username(session: AsyncSession, email: str, max_attempts: int = 10) -> str:
    base_username = f"@{email.split('@')[0][:16].lower()}"
    if _check_username_exists(session, base_username):
        return base_username
    
    for _ in range(max_attempts):
        username = f"{base_username}.{secrets.token_hex(1)}"
        if await _check_username_exists(session, username):
            return username
        
    return f"{base_username}.{secrets.token_hex(2)}"


async def create_author_db(session: AsyncSession, author: CreateAuthorSchema) -> AuthorResponseSchema:
    hashed_password = hash_password(author.password)
    try:
        first_name = author.first_name.strip().capitalize()
        last_name = author.last_name.strip().capitalize() if author.last_name else None
        email = author.email

        unique_username = await generate_unique_username(session, email)

        users_stmt = insert(Users).values(
            first_name=first_name,
            last_name=last_name,
            username=unique_username,
            email=author.email,
            password=hashed_password,
            role=UserRoles.CREATOR
        ).returning(
            Users.id,
            Users.first_name,
            Users.last_name,
            Users.username,
            Users.email,
            Users.role
        )
        res = await session.execute(users_stmt)
        user = res.first()

        authors_stmt = insert(Authors).values(
            id=user.id,
            bio=author.bio
        ).returning(
            Authors.bio
        )
        res = await session.execute(authors_stmt)
        bio = res.scalar_one_or_none()
        await session.commit()

        return AuthorResponseSchema(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            bio=bio
        )
        
    except IntegrityError as ie:
        print(ie, ie.detail)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='author already exists'
        )
    

async def get_author_profile_db(session: AsyncSession, curr_creator: Users):
    query = select(Authors).join(Users, onclause=Authors.id == Users.id).where(Users.id == curr_creator.id)
    res = await session.execute(query)
    creator = res.first()
    return creator

async def update_creator_password(session: AsyncSession, curr_creator: Users, old_password: str, new_password: str):
    if not verify_pw(old_password, curr_creator.password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="incorrect password"
        )
    new_hashed_password = hash_password(new_password)

    try:
        await session.execute(
            update(Users).values(password = new_hashed_password).where(Users.email == curr_creator.email)
        )
        await session.commit()
        return {"status": "success"}
    except Exception as e:
        await session.rollback()
        msg = str(e)
        print(f"Unknown error while updating password: {msg}")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=msg
        )
    
async def update_creator_profile_db(session: AsyncSession, curr_creator: Users, body: UpdateProfileSchema):
    profile_dict = body.model_dump(exclude_none=True)
    try:
        user_fields = {key: val for key, val in profile_dict.items() if key in ['first_name', 'last_name']}
        if user_fields:
            await session.execute(update(Users).values(**user_fields).where(Users.id == curr_creator.id))
        if 'bio' in profile_dict:
            await session.execute(update(Authors).values(bio=profile_dict['bio']).where(Authors.id == curr_creator.id))

        await session.commit()
        updated_creator = await session.execute(select(Users, Authors).join(Authors, onclause=Users.id == Authors.id).where(Users.id == curr_creator.id))
        return updated_creator
    except DatabaseError as dbe:
        msg = f"Unknown error while updating creator profile: {str(dbe)}"
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=msg
        )
    