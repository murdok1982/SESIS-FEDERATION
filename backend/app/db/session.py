# -*- coding: utf-8 -*-
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, pool_size=10, max_overflow=20)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def check_db_connected():
    async with engine.connect() as conn:
        await conn.execute("SELECT 1")


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
