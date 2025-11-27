from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, DatabaseError
from sqlalchemy import select, update
from fastapi import HTTPException, status, UploadFile
import secrets
from typing import Any

from src.creators.schemas import CreateAuthorSchema, AuthorResponseSchema, UpdateProfileSchema
from src.models import Authors, Users, UserRoles
from src.creators.utils import hash_password
from src.auth.utils import verify_pw
from src.aws.service import upload_file
from src.aws.utils import get_full_s3_object_url

async def _check_username_exists(session: AsyncSession, username: str) -> bool:
    existing_user = await session.scalar(
        select(Users).where(Users.username == username)
    )
    return existing_user is not None

async def generate_unique_username(session: AsyncSession, email: str, max_attempts: int = 10) -> str:
    base_username = f"@{email.split('@')[0][:16].lower()}"
    if not await _check_username_exists(session, base_username):
        return base_username
    
    for _ in range(max_attempts):
        username = f"{base_username}.{secrets.token_hex(1)}"
        if not await _check_username_exists(session, username):
            return username
        
    return f"{base_username}.{secrets.token_hex(2)}"


async def create_author_db(
    session: AsyncSession,
    s3,
    first_name: str,
    email: str,
    password: str,
    phone: str | None = None,
    last_name: str | None = None,
    bio: str | None = None,
    profile_image: UploadFile | None = None
) -> AuthorResponseSchema:
    hashed_password = hash_password(password)
    try:
        first_name = first_name.strip().capitalize()
        last_name = last_name.strip().capitalize() if last_name else None

        unique_username = await generate_unique_username(session, email)

        key = await upload_file(
            s3,
            file=profile_image,
            username=unique_username,
            folder='profile_images'
        )

        users_stmt = insert(Users).values(
            first_name=first_name,
            last_name=last_name,
            username=unique_username,
            email=email,
            password=hashed_password,
            phone=phone,
            profile_image_key=key or None,
            role=UserRoles.CREATOR,
            active=False
        ).returning(
            Users.id,
            Users.first_name,
            Users.last_name,
            Users.username,
            Users.email,
            Users.phone,
            Users.role,
            Users.profile_image_key
        )
        res = await session.execute(users_stmt)
        user = res.first()

        authors_stmt = insert(Authors).values(
            id=user.id,
            bio=bio
        ).returning(
            Authors.bio
        )
        res = await session.execute(authors_stmt)
        bio = res.scalar_one_or_none()
        await session.commit()

        profile_img_url = get_full_s3_object_url(user.profile_image_key) if key is not None else None 

        return AuthorResponseSchema(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=unique_username,
            email=user.email,
            bio=bio,
            profile_image=profile_img_url
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
    
async def update_creator_profile_db(
    session: AsyncSession,
    s3,
    curr_creator: Users,
    first_name: str | None = None,
    last_name: str | None = None,
    bio: str | None = None,
    profile_image: UploadFile | None = None
):
    # ---------- Update Users table ----------
    user_updates = {}
    
    if first_name is not None:
        user_updates['first_name'] = first_name

    if last_name is not None:
        user_updates['last_name'] = last_name

    if profile_image is not None:
        key = await upload_file(
            s3,
            file=profile_image,
            username=curr_creator.username,
            folder='profile_images'
        )
        if key:
            user_updates['profile_image_key'] = key

    if user_updates:
        await session.execute(
            update(Users)
            .where(Users.id == curr_creator.id)
            .values(user_updates)
        )

    # ---------- Handle Authors table (lazy create/update) ----------
    if bio is not None:
        # Check if Authors record exists
        result = await session.execute(
            select(Authors).where(Authors.user_id == curr_creator.id)
        )
        author_row = result.scalar_one_or_none()

        if author_row is None:
            # Create new author row
            new_author = Authors(
                user_id=curr_creator.id,
                bio=bio
            )
            session.add(new_author)
        else:
            # Update existing author bio
            await session.execute(
                update(Authors)
                .where(Authors.user_id == curr_creator.id)
                .values(bio=bio)
            )

    # ---------- Commit everything ----------
    await session.commit()
    await session.refresh(curr_creator)

    # Fetch updated author profile
    result = await session.execute(
        select(Authors).where(Authors.user_id == curr_creator.id)
    )
    author_profile = result.scalar_one_or_none()

    return AuthorResponseSchema(
        id=curr_creator.id,
        first_name=curr_creator.first_name,
        last_name=curr_creator.last_name,
        email=curr_creator.email,
        username=curr_creator.username,
        bio=author_profile.bio if author_profile else None,
        profile_image=get_full_s3_object_url(curr_creator.profile_image_key)
    )


    
    