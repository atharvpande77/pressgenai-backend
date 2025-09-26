from fastapi import Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_session
from src.auth.service import get_user_by_email
from src.auth.utils import decrypt_jwt

Session = Annotated[AsyncSession, Depends(get_session)]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(session: Session, token: Annotated[str, Depends(oauth2_scheme)]):
    jwt_payload = decrypt_jwt(token)
    if not jwt_payload:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="invalid token"
        )
    email = jwt_payload.get('email')
    user = await get_user_by_email(session, email)
    if not user:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail='user not found'
        )
    return user