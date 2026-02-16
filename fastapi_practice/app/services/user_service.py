from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import hash_password, verify_password
from app.core.exceptions import NotFoundError, ConflictError, AuthenticationError


class UserService:
    def __init__(self, db: AsyncSession):
        self.repository = UserRepository(db)
    
    async def create_user(self, user_data: UserCreate) -> User:
        # Check for existing email
        if await self.repository.get_by_email(user_data.email):
            raise ConflictError("Email already registered")
        
        # Check for existing username
        if await self.repository.get_by_username(user_data.username):
            raise ConflictError("Username already taken")
        
        # Create user with hashed password
        user = User(
            email=user_data.email,
            username=user_data.username,
            hashed_password=hash_password(user_data.password),
        )
        
        return await self.repository.create(user)
    
    async def get_user(self, user_id: int) -> User:
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User with id {user_id} not found")
        return user
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        return await self.repository.get_by_email(email)
    
    async def get_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        return await self.repository.get_all(skip=skip, limit=limit)
    
    async def update_user(self, user_id: int, user_data: UserUpdate) -> User:
        user = await self.get_user(user_id)
        
        # Check for email conflict
        if user_data.email and user_data.email != user.email:
            if await self.repository.get_by_email(user_data.email):
                raise ConflictError("Email already registered")
        
        # Check for username conflict
        if user_data.username and user_data.username != user.username:
            if await self.repository.get_by_username(user_data.username):
                raise ConflictError("Username already taken")
        
        # Update fields
        update_data = user_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        
        return await self.repository.update(user)
    
    async def delete_user(self, user_id: int) -> None:
        user = await self.get_user(user_id)
        await self.repository.delete(user)
    
    async def authenticate(self, email: str, password: str) -> User:
        user = await self.repository.get_by_email(email)
        
        if not user or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")
        
        if not user.is_active:
            raise AuthenticationError("User account is inactive")
        
        return user
