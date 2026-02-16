from fastapi import FastAPI, HTTPException
from schemas.item import Post_create, Post_response
from typing import List
from app.db import Post,create_db,get_db

app = FastAPI()

text_post={
    1:{"title":"Post 1","content":"Content 1"},
    2:{"title":"Post 2","content":"Content 2"},
    3:{"title":"Post 3","content":"Content 3"},
    4:{"title":"Post 4","content":"Content 4"},
    5:{"title":"Post 5","content":"Content 5"}}

@app.get('/posts', response_model=List[Post_response])
def get_all_posts(limit:int=None):
    if limit:
        return list(text_post.values())[:limit]
    return text_post

@app.get('/posts/{post_id}') # example of a dynamic value
def get_post(post_id: int):
    return text_post.get(post_id)
    if post_id not in text_post:
        raise HTTPException(status_code=404, detail="Post not found")

@app.post('/posts', tags=['posts'])
def create_post(post: Post_create): #: means that the post is a Post_create object
    return {"data": post}
