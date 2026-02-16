from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.item import Item


class ItemRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create(self, item: Item) -> Item:
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item
    
    async def get_by_id(self, item_id: int) -> Optional[Item]:
        result = await self.db.execute(
            select(Item).where(Item.id == item_id)
        )
        return result.scalar_one_or_none()
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Item]:
        result = await self.db.execute(
            select(Item).offset(skip).limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_by_owner(self, owner_id: int, skip: int = 0, limit: int = 100) -> List[Item]:
        result = await self.db.execute(
            select(Item)
            .where(Item.owner_id == owner_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def update(self, item: Item) -> Item:
        await self.db.flush()
        await self.db.refresh(item)
        return item
    
    async def delete(self, item: Item) -> None:
        await self.db.delete(item)
        await self.db.flush()
