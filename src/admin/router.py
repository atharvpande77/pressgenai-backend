from fastapi import APIRouter, Depends, status, HTTPException
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from src.auth.dependencies import role_checker
from src.config.database import get_session
from src.models import Users, UserRoles
from src.admin.schemas import NewUserSchema
from src.creators.utils import hash_password

router = APIRouter()

@router.post('/')
async def add_new_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    curr_admin: Annotated[Users, Depends(role_checker(UserRoles.ADMIN))],
    new_user: NewUserSchema
):
    hashed_password = hash_password(new_user.password)
    new_user_dict = new_user.model_dump(exclude_none=True)
    new_user_dict['password'] = hashed_password
    result = await session.execute(
        insert(Users)
        .values(new_user_dict)
        .returning(Users)
    )
    new_user_db = result.scalars().all()
    return new_user_db
