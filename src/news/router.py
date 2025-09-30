from fastapi import APIRouter, Depends
from typing import Annotated
from sqlalchemy.dialects.postgresql import AsyncSession
from sqlalchemy.exc import DatabaseError
from sqlalchemy import select

from src.config.database import get_session
from src.models import GeneratedUserStories

router = APIRouter()

@router.get('/')
async def get_all_articles(
    session: Annotated[AsyncSession, Depends(get_session)],
    category: str | None = None,
    limit: int | None = 10,
    offset: int| None = 0
):
    result = await session.execute(
        select(GeneratedUserStories)
        .where()
    )