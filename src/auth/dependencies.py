from fastapi import Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_session
from src.auth.service import get_user_by_email
from src.auth.utils import decrypt_jwt
from src.models import Users

Session = Annotated[AsyncSession, Depends(get_session)]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(session: Session, token: Annotated[str, Depends(oauth2_scheme)]):
    jwt_payload = decrypt_jwt(token)
    if not jwt_payload:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    email = jwt_payload.get('email')
    if not email:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required claims",
            headers={"WWW-Authenticate": "Bearer"}
        )
    user = await get_user_by_email(session, email)
    if not user:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail='user not found'
        )
    return user

def role_checker(*args):
    def wrapper(curr_user: Annotated[Users, Depends(get_current_user)]):
        if curr_user.role not in args:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="not allowed"
            )
        return curr_user
    return wrapper
        

