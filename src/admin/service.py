from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from uuid import UUID
from datetime import datetime, timedelta

from src.creators.service import generate_unique_username
from src.models import Users, UserRoles, EditorCategories, EditorCities

async def store_user(
    session: AsyncSession, # Don't commit; part of transaction
    admin_id: UUID,
    email: str,
    password: str,
    first_name: str,
    role: UserRoles,
    last_name: str | None = None,
    phone: str | None = None,
):
    username = await generate_unique_username(session, email)
    
    result = await session.execute(
        insert(Users)
            .values(
                email=email,
                password=password,
                first_name=first_name,
                role=role,
                last_name=last_name,
                phone=phone,
                username=username,
                added_by=admin_id,
                approved_by=admin_id,
                approved_at=datetime.now()+timedelta(hours=5, minutes=30),
            )
            .returning(Users)
    )
    user = result.scalar_one_or_none()
    return user


async def store_editor_cities_and_categories(
    session: AsyncSession,
    editor_id: UUID,
    city_ids: list[UUID],
    category_ids: list[UUID]
):
    # Clear existing relations in one go
    await session.execute(
        delete(EditorCities).where(EditorCities.editor_id == editor_id)
    )
    await session.execute(
        delete(EditorCategories).where(EditorCategories.editor_id == editor_id)
    )

    if city_ids:
        await session.execute(
            insert(EditorCities),
            [{"editor_id": editor_id, "city_id": cid} for cid in city_ids],
        )

    if category_ids:
        await session.execute(
            insert(EditorCategories),
            [{"editor_id": editor_id, "category_id": cat_id} for cat_id in category_ids],
        )
    