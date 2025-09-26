from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from src.config.settings import settings


engine = create_async_engine(url=settings.POSTGRES_CNX_STR_LOCAL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_session():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()