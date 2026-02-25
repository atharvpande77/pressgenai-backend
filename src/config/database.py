from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from typing import Annotated
from fastapi import Depends

from src.config.settings import settings

environment=settings.ENV
if environment == 'dev':
    url = settings.DEV_DB_CNX_STR
else:
    url = settings.POSTGRES_CNX_STR_LOCAL

engine = create_async_engine(url=url)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_session():
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
            
Session = Annotated[AsyncSession, Depends(get_session)]