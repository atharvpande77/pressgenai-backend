import httpx
from src.utils.sources import RSS_FEEDS_SOURCES

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas import LocationDataSchema
from sqlalchemy import select, and_, or_
from src.models import Locations




async def get_locations_status(session: AsyncSession, location: LocationDataSchema):
    query = select(Locations).filter(
        or_(
            and_(
                Locations.city == location.city,
                Locations.state == location.state,
                Locations.country == location.country,
                Locations.level == 'city'
            ),
            and_(
                Locations.state == location.state,
                Locations.country == location.country,
                Locations.level == 'state'
            ),
            and_(
                Locations.country == location.country,
                Locations.level == 'country'
            ),
            Locations.level == 'world'
        )
    )
    locations_status = await session.execute(query)
    return {loc.level: loc for loc in locations_status.scalars().all()}



def check_data_freshness(location: LocationDataSchema):
    ...


# async def fetch_and_store_news(session: AsyncSession, location: LocationDataSchema, levels_to_fetch: list, existing_locations: dict):
#     for level in levels_to_fetch:
#         if level not in existing_locations:
#             location_record = create_location_record(session, location, level)
#             existing_locations[level] = location_record

#     new_stories = await fetch_from_news_api(location_data, levels_to_fetch)

# def get_relative_time(publish_date: str) -> str:
#         """Convert publication date to relative time string"""
#         now = datetime.now()
#         # diff = now - 
        
#         if diff.days > 0:
#             return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
#         elif diff.seconds > 3600:
#             hours = diff.seconds // 3600
#             return f"{hours} hour{'s' if hours > 1 else ''} ago"
#         elif diff.seconds > 60:
#             minutes = diff.seconds // 60
#             return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
#         else:
#             return "Just now"