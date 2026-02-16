from collections.abc import AsyncGenerator
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


DATABASE_URL="sqlite+aiosqlite:///./test.db" # helps us connect to our local db file

#data models is type of data we want to store ie the structure and typoe
#uuid-random unique id which will be the primary key

class Base(DeclarativeBase):
    pass


class Post(Base):
    __tablename__="posts"

    id=Column(UUID(as_uuid=True), primary_key=True,default=uuid.uuid4)
    caption=Column(Text)
    url=Column(String,nullable=False)
    file_type=Column(String,nullable=False)
    file_name=Column(String,nullable=False)
    created_at=Column(DateTime,default=datetime.utcnow)


engine = create_async_engine(DATABASE_URL, echo=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def create_db():
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db():
    """Drop all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()