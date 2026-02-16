from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


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