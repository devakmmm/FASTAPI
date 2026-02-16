from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ItemBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None


class ItemResponse(ItemBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class Post_create(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    published: bool = Field(default=True)
    rating: Optional[int] = Field(default=None, ge=1, le=5)

class Post_response(BaseModel):
    id: int
    title: str
    content: str
    published: bool
    rating: Optional[int] = Field(default=None, ge=1, le=5)

class Post_update(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = Field(default=None, min_length=1)
    published: Optional[bool] = Field(default=None)
