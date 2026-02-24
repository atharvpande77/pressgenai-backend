from fastapi import APIRouter
from sqlalchemy import select

from src.config.database import Session
from src.models import Categories, Cities
from src.common.schemas import CategoryItem, CityItem

router = APIRouter()

@router.get(
    '/categories',
    response_model=list[CategoryItem],
    summary="Retrieve all active categories",
    description="""Fetch a paginated list of all active article categories.
    
    Returns categories that are currently active in the system.
    Useful for filtering articles or populating category selection dropdowns.""",
    responses={
        200: {"description": "Successfully retrieved categories list"},
        500: {"description": "Internal server error while fetching categories"}
    }
)
async def get_all_categories(
    session: Session,
    limit: int = 20
):
    result = await session.execute(
        select(Categories)
            .where(Categories.active == True)
            .limit(limit)
    )
    return result.scalars().all()
    
    
@router.get(
    '/cities',
    response_model=list[CityItem],
    summary="Retrieve all active cities",
    description="""Fetch a paginated list of all active cities in the system.
    
    Returns cities that are currently active and available for article location assignment.
    Useful for filtering articles or populating city selection dropdowns.""",
    responses={
        200: {"description": "Successfully retrieved cities list"},
        500: {"description": "Internal server error while fetching cities"}
    }
)
async def get_all_cities(
    session: Session,
    limit: int = 20
):
    result = await session.execute(
        select(Cities)
            .where(Cities.active == True)
            .limit(limit)
    )
    return result.scalars().all()