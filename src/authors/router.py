from fastapi import APIRouter, Depends, status
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_session
from src.authors.schemas import CreateAuthorSchema, AuthorResponseSchema
from src.authors.service import create_author_db


router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]

@router.post('/', status_code=status.HTTP_201_CREATED, response_model=AuthorResponseSchema)
async def create_author(session: Session, author: CreateAuthorSchema):
    return await create_author_db(session, author)