from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from src.authors.schemas import CreateAuthorSchema, AuthorResponseSchema
from src.models import Authors, Users, UserRoles
from src.authors.utils import hash_password


async def create_author_db(session: AsyncSession, author: CreateAuthorSchema) -> AuthorResponseSchema:
    hashed_password = hash_password(author.password)
    try:
        users_stmt = insert(Users).values(
            first_name=author.first_name,
            last_name=author.last_name,
            email=author.email,
            password=hashed_password,
            role=UserRoles.CREATOR
        ).returning(
            Users.id,
            Users.first_name,
            Users.last_name,
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
        print(ie)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='author already exists'
        )