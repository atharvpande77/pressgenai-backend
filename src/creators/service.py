from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, DatabaseError
from sqlalchemy import select, update, delete
from fastapi import HTTPException, status, UploadFile
import secrets
from typing import Any
from uuid import UUID
import logging

from src.creators.schemas import (
    CreateAuthorSchema,
    AuthorResponseSchema,
    UpdateProfileSchema,
    CreatorLink,
    CreatorOnboardingStatus,
)
from src.models import Authors, Users, UserRoles, Cities
from src.creators.utils import hash_password
from src.auth.utils import verify_pw
from src.aws.service import upload_file

logger = logging.getLogger(__name__)

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
    city_id: UUID,
    phone: str | None = None,
    last_name: str | None = None,
    bio: str | None = None,
    profile_image: UploadFile | None = None
) -> AuthorResponseSchema:
    
    # Verify city id exists
    city = await session.get(Cities, city_id)
    if not city:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="city id does not exist"
        )
    
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
            bio=bio,
            city_id=city_id
        ).returning(
            Authors.bio,
            Authors.city_id
        )
        res = await session.execute(authors_stmt)
        bio = res.scalar_one_or_none()
        await session.commit()

        profile_image_key = key or None

        return AuthorResponseSchema(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=unique_username,
            email=user.email,
            bio=bio,
            city=city.name if city else None,
            city_id=city_id if city else None,
            profile_image_key=profile_image_key
        )
        
    except IntegrityError as ie:
        await session.rollback()
        logger.exception("Creator already exists", extra={"event": "creator.create", "email": email})
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
        logger.exception("Failed to update creator password", extra={"event": "creator.password_update", "creator_id": curr_creator.id})
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
            select(Authors).where(Authors.id == curr_creator.id)
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
            result = await session.execute(
                update(Authors)
                    .where(Authors.id == curr_creator.id)
                    .values(bio=bio)
            )

    # ---------- Commit everything ----------
    await session.commit()
    await session.refresh(curr_creator)

    # Fetch updated author profile
    result = await session.execute(
        select(Authors).where(Authors.id == curr_creator.id)
    )
    author_profile = result.scalar_one_or_none()

    return AuthorResponseSchema(
        id=curr_creator.id,
        first_name=curr_creator.first_name,
        last_name=curr_creator.last_name,
        email=curr_creator.email,
        username=curr_creator.username,
        bio=author_profile.bio if author_profile else None,
        profile_image_key=curr_creator.profile_image_key
    )


from sqlalchemy import delete
from datetime import date

from src.models import EditorCities, UserLinks

async def store_creator_onboarding(
    session: AsyncSession,
    creator_id: UUID,
    date_of_birth: date | None = None,
    city_id: UUID | None = None,
    highest_education: str | None = None,
    work_status: str | None = None,
    highest_educatation_specify: str | None = None,
    work_status_specify: str | None = None,
):
    author = await session.get(Authors, creator_id)
    if not author:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Creator profile not found")

    if date_of_birth is not None:
        author.date_of_birth = date_of_birth

    if highest_education is not None:
        author.highest_education = highest_education

    if work_status is not None:
        author.work_status = work_status

    if highest_educatation_specify is not None:
        author.highest_education_other_specify = highest_educatation_specify

    if work_status_specify is not None:
        author.work_status_other_specify = work_status_specify

    if city_id is not None:
        city = await session.get(Cities, city_id)
        if not city:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="invalid city id",
            )
        author.city_id = city_id

    return author

async def _delete_existing_links_or_cities(session: AsyncSession, table: EditorCities | UserLinks, creator_id: UUID):
    column = getattr(table, "editor_id", None) or getattr(table, "user_id", None)
    if column is None:
        raise RuntimeError("Unable to determine foreign key column for deletion")
    await session.execute(
        delete(table).where(column == creator_id)
    )

async def store_creator_links(
    session: AsyncSession,
    creator_id: UUID,
    links: list[CreatorLink]
):
    await _delete_existing_links_or_cities(session, UserLinks, creator_id)
    
    await session.execute(
        insert(UserLinks)
            .values([{"user_id": creator_id, "url": str(link.url), "link_type": link.link_type, "platform": link.platform, "description": link.description} for link in links])
    )


async def fetch_creator_onboarding_status(
    session: AsyncSession,
    creator_id: UUID
) -> CreatorOnboardingStatus | None:
    author_profile = await session.get(Authors, creator_id)
    if not author_profile:
        return None

    links_stmt = await session.execute(
        select(UserLinks).where(UserLinks.user_id == creator_id)
    )
    stored_links = links_stmt.scalars().all()

    creator_links = [
        CreatorLink(
            link_type=link.link_type,
            url=link.url,
            platform=link.platform,
            description=link.description,
        )
        for link in stored_links
    ]

    creator_city = author_profile.city

    return CreatorOnboardingStatus(
        date_of_birth=author_profile.date_of_birth,
        highest_education=author_profile.highest_education,
        highest_education_other_specify=author_profile.highest_education_other_specify,
        work_status=author_profile.work_status,
        work_status_other_specify=author_profile.work_status_other_specify,
        city_id=creator_city.id if creator_city else None,
        city=creator_city.name if creator_city else None,
        links=creator_links,
        onboarding_completed=author_profile.onboarding_completed,
    )
    

async def update_onboarding_status(
    session: AsyncSession,
    creator_id: UUID,
    completed: bool
):
    await session.execute(
        update(Authors)
            .where(Authors.id == creator_id)
            .values(onboarding_completed=completed)
    )

async def complete_creator_onboarding(
    session: AsyncSession,
    creator_id: UUID,
    date_of_birth: date | str,
    city_id: UUID,
    highest_education: str,
    work_status: str,
    city_ids: list[UUID],
    education_other_specify: str | None = None,
    work_status_other_specify: str | None = None,
    links: list[CreatorLink] | None = None,
):
    await store_creator_onboarding(
            session=session,
            creator_id=creator_id,
            date_of_birth=date_of_birth,
            city_id=city_id,
            highest_education=highest_education,
            highest_educatation_specify=education_other_specify,
            work_status=work_status,
            work_status_specify=work_status_other_specify,
        )
    
    if links:
        await store_creator_links(session, creator_id, links)
        
    
    await update_onboarding_status(session, creator_id, True)
        
    return None

