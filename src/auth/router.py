from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta

from src.config.database import get_session
from src.auth.service import get_user_by_email
from src.auth.utils import verify_pw, create_tokens
from src.auth.schemas import LoginResponse
from src.auth.dependencies import get_current_user


router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

@router.post('/', response_model=LoginResponse)
async def login(session: Session, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = await get_user_by_email(session, form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is banned/not approved yet.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_pw(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token, refresh_token = create_tokens(
        data = {"sub": str(user.id), "email": user.email, "role": user.role},
        access_exp_delta = timedelta(minutes=24*60),
        refresh_exp_delta = timedelta(days=30)
    )
    
    return LoginResponse(
        access_token=access_token,
        token_type='bearer',
        expires_in=24*60*60,
        user=user
    )
