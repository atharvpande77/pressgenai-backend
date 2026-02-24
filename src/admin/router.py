from fastapi import APIRouter, Depends, status, HTTPException
from typing import Annotated
from sqlalchemy.dialects.postgresql import insert

from src.auth.dependencies import role_checker
from src.config.database import Session
from src.models import Users, UserRoles
from src.admin.schemas import NewInvite, NewUserSchema
from src.creators.utils import hash_password
from src.admin.service import store_user, store_editor_cities_and_categories
from src.creators.service import complete_creator_onboarding

router = APIRouter()

admin_role_dep = Annotated[Users, Depends(role_checker(UserRoles.ADMIN))]


@router.post('/')
async def add_new_user(
    session: Session,
    curr_admin: admin_role_dep,
    new_user: NewUserSchema
):
    hashed_password = hash_password(new_user.password)
    new_user_dict = new_user.model_dump(exclude_none=True)
    new_user_dict['password'] = hashed_password
    role = new_user_dict['role']
    
    async with session.begin():
        user = await store_user(
            session=session,
            admin_id=curr_admin.id,
            email=new_user_dict['email'],
            password=hashed_password,
            first_name=new_user_dict['first_name'],
            role=role,
            last_name=new_user_dict.get('last_name'),
            phone=new_user_dict.get('phone'),
        )
        user_id = user.id
    
        if role == UserRoles.CREATOR:
            await complete_creator_onboarding(
                session=session,
                creator_id=user_id,
                date_of_birth=new_user_dict.get('date_of_birth'),
                city_id=new_user_dict.get('city_ids', [None])[0],  # Get the single city_id for creator
                highest_education=new_user_dict.get('highest_education'),
                work_status=new_user_dict.get('work_status'),
                education_other_specify=new_user_dict.get('education_other_specify'),
                work_status_other_specify=new_user_dict.get('work_status_other_specify'),
                links=new_user_dict.get('links')
            )
        elif role == UserRoles.EDITOR:            
            await store_editor_cities_and_categories(
                session=session,
                editor_id=user_id,
                city_ids=new_user_dict.get('city_ids', []),
                category_ids=new_user_dict.get('category_ids', [])
            )
                    
    return user


@router.post('/invites')
async def invite_user(
    session: Session,
    curr_admin: admin_role_dep,
    new_invite: NewInvite
):
    ...
    
    
@router.post('/invites/accept')
async def accept_invite(
    session: Session,
    invite_token: str
):
    ...
