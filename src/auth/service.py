from fastapi import status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.schemas import AuthSchema
from src.models import Authors, Users


async def get_user_by_email(session: AsyncSession, email: str):
    result = await session.execute(select(Users).filter(Users.email == email))
    return result.scalars().first()
    

