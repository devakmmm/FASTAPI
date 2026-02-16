from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.item import Item
from app.repositories.item_repository import ItemRepository
from app.schemas.item import ItemCreate, ItemUpdate
from app.core.exceptions import NotFoundError, AuthorizationError


class ItemService:
    def __init__(self, db: AsyncSession):
        self.repository = ItemRepository(db)
    
    async def create_item(self, item_data: ItemCreate, owner_id: int) -> Item:
        item = Item(
            title=item_data.title,
            description=item_data.description,
            owner_id=owner_id,
        )
        return await self.repository.create(item)
    
    async def get_item(self, item_id: int) -> Item:
        item = await self.repository.get_by_id(item_id)
        if not item:
            raise NotFoundError(f"Item with id {item_id} not found")
        return item
    
    async def get_items(self, skip: int = 0, limit: int = 100) -> List[Item]:
        return await self.repository.get_all(skip=skip, limit=limit)
    
    async def get_user_items(self, owner_id: int, skip: int = 0, limit: int = 100) -> List[Item]:
        return await self.repository.get_by_owner(owner_id, skip=skip, limit=limit)
    
    async def update_item(self, item_id: int, item_data: ItemUpdate, user_id: int) -> Item:
        item = await self.get_item(item_id)
        
        # Check ownership
        if item.owner_id != user_id:
            raise AuthorizationError("You don't have permission to update this item")
        
        # Update fields
        update_data = item_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(item, field, value)
        
        return await self.repository.update(item)
    
    async def delete_item(self, item_id: int, user_id: int) -> None:
        item = await self.get_item(item_id)
        
        # Check ownership
        if item.owner_id != user_id:
            raise AuthorizationError("You don't have permission to delete this item")
        
        await self.repository.delete(item)
