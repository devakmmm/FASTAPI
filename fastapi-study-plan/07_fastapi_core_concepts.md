# Module 07: FastAPI Core Concepts

## Learning Objectives

By the end of this module, you will be able to:

- Explain what ASGI is and how uvicorn fits in
- Create a FastAPI application from scratch
- Define routes with all HTTP methods
- Use path parameters, query parameters, and request bodies
- Validate input with Pydantic models
- Define response models
- Use dependency injection
- Add middleware
- Handle errors properly
- Configure CORS
- Use background tasks

---

## 7.1 What Is FastAPI?

FastAPI is a modern Python web framework for building APIs. It was created by Sebastián Ramírez and released in 2018. It is built on:

- **Starlette** — async web framework (handles HTTP, WebSockets, routing)
- **Pydantic** — data validation (handles models, serialization)
- **Python type hints** — drives auto-validation and auto-documentation

### Why FastAPI?

| Feature | Flask | Django REST | FastAPI |
|---------|-------|-------------|---------|
| Async native | No | No | Yes |
| Auto validation | No | Partial | Yes |
| Auto docs (OpenAPI) | No | Via DRF | Yes |
| Type hint driven | No | No | Yes |
| Performance | Moderate | Moderate | High |
| Learning curve | Low | High | Moderate |

FastAPI generates interactive API documentation (Swagger UI and ReDoc) automatically from your code. No extra configuration.

---

## 7.2 ASGI and uvicorn

### ASGI (Asynchronous Server Gateway Interface)

ASGI is a specification that defines how Python web servers communicate with web applications. It is the async successor to WSGI.

```
┌──────────────────┐     ASGI      ┌──────────────────┐
│   uvicorn        │ ◄───────────► │   FastAPI        │
│   (ASGI server)  │   protocol    │   (ASGI app)     │
│                  │               │                  │
│   Handles:       │               │   Handles:       │
│   - TCP          │               │   - Routing      │
│   - HTTP parsing │               │   - Validation   │
│   - Connections  │               │   - Business     │
│   - Workers      │               │     logic        │
└──────────────────┘               └──────────────────┘
```

**uvicorn** is the ASGI server. It handles the low-level networking. FastAPI is the application. It handles the logic.

Analogy: uvicorn is the mail carrier. FastAPI is the person who reads and responds to the mail.

---

## 7.3 Your First FastAPI Application

### Setup

```bash
mkdir fastapi-learn && cd fastapi-learn
python3 -m venv .venv
source .venv/bin/activate
pip install "fastapi[standard]"
```

### The Minimal App

```python
# main.py
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello, World"}
```

### Run It

```bash
uvicorn main:app --reload
```

Breaking this down:
- `main` — the file (`main.py`)
- `app` — the FastAPI instance variable
- `--reload` — auto-restart on code changes (development only)

### Verify

```bash
# In another terminal
curl http://localhost:8000
# {"message":"Hello, World"}

curl http://localhost:8000/docs
# Opens Swagger UI (interactive documentation)

curl http://localhost:8000/redoc
# Opens ReDoc (alternative documentation)

curl http://localhost:8000/openapi.json
# Raw OpenAPI specification
```

**Open http://localhost:8000/docs in your browser.** This is automatically generated from your code. You will use this constantly.

---

## 7.4 Routing

Routes map HTTP methods + URL paths to handler functions.

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
async def list_users():
    return [{"id": 1, "name": "Alice"}]

@app.post("/users")
async def create_user():
    return {"id": 2, "name": "New User"}

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id, "name": "Alice"}

@app.put("/users/{user_id}")
async def replace_user(user_id: int):
    return {"id": user_id, "updated": True}

@app.patch("/users/{user_id}")
async def update_user(user_id: int):
    return {"id": user_id, "patched": True}

@app.delete("/users/{user_id}")
async def delete_user(user_id: int):
    return {"id": user_id, "deleted": True}
```

### Route Order Matters

```python
@app.get("/users/me")            # MUST come before /users/{user_id}
async def get_current_user():
    return {"id": 1, "name": "Current User"}

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id}
```

If `/users/{user_id}` comes first, `/users/me` would match with `user_id = "me"` and fail because "me" is not an `int`.

### APIRouter — Organizing Routes

For larger applications, group routes into routers:

```python
# app/routes/users.py
from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/")
async def list_users():
    return []

@router.get("/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id}

@router.post("/")
async def create_user():
    return {"created": True}
```

```python
# app/main.py
from fastapi import FastAPI
from app.routes import users

app = FastAPI()
app.include_router(users.router)
```

---

## 7.5 Path Parameters

Path parameters are parts of the URL path that vary.

```python
@app.get("/users/{user_id}")
async def get_user(user_id: int):     # Automatically converted to int
    return {"user_id": user_id}

@app.get("/files/{file_path:path}")   # Captures full path including slashes
async def get_file(file_path: str):
    return {"path": file_path}
```

```bash
curl http://localhost:8000/users/42
# {"user_id": 42}

curl http://localhost:8000/users/abc
# 422 Unprocessable Entity — "abc" is not an integer

curl http://localhost:8000/files/docs/readme.md
# {"path": "docs/readme.md"}
```

### Enum Path Parameters

```python
from enum import Enum

class UserRole(str, Enum):
    admin = "admin"
    user = "user"
    moderator = "moderator"

@app.get("/users/role/{role}")
async def get_users_by_role(role: UserRole):
    return {"role": role, "message": f"Fetching {role.value} users"}
```

```bash
curl http://localhost:8000/users/role/admin    # Works
curl http://localhost:8000/users/role/guest    # 422 — not a valid role
```

---

## 7.6 Query Parameters

Any function parameter that is NOT a path parameter becomes a query parameter.

```python
@app.get("/users")
async def list_users(
    skip: int = 0,
    limit: int = 10,
    role: str | None = None,
    active: bool = True,
):
    return {
        "skip": skip,
        "limit": limit,
        "role": role,
        "active": active,
    }
```

```bash
curl "http://localhost:8000/users"
# {"skip":0,"limit":10,"role":null,"active":true}

curl "http://localhost:8000/users?skip=20&limit=50&role=admin&active=false"
# {"skip":20,"limit":50,"role":"admin","active":false}

curl "http://localhost:8000/users?limit=abc"
# 422 — "abc" is not an integer
```

### Required vs Optional

```python
@app.get("/search")
async def search(
    q: str,                     # Required — no default value
    page: int = 1,              # Optional — has default
    category: str | None = None # Optional — explicitly nullable
):
    return {"q": q, "page": page, "category": category}
```

```bash
curl "http://localhost:8000/search"
# 422 — "q" is required

curl "http://localhost:8000/search?q=python"
# {"q":"python","page":1,"category":null}
```

### Advanced Query Parameters with `Query`

```python
from fastapi import Query

@app.get("/items")
async def list_items(
    q: str | None = Query(
        default=None,
        min_length=3,
        max_length=50,
        description="Search query",
        examples=["laptop"],
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    size: int = Query(default=20, ge=1, le=100, description="Page size"),
):
    return {"q": q, "page": page, "size": size}
```

---

## 7.7 Request Body with Pydantic Models

```python
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    age: int = Field(ge=0, le=150)
    bio: str | None = None

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    age: int
    bio: str | None

@app.post("/users", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate):
    # In reality, save to database here
    return UserResponse(
        id=42,
        name=user.name,
        email=user.email,
        age=user.age,
        bio=user.bio,
    )
```

```bash
# Valid request
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com", "age": 30}'

# Response: {"id":42,"name":"Alice","email":"alice@example.com","age":30,"bio":null}

# Invalid — missing required field
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice"}'

# 422 — email is required, age is required

# Invalid — bad email
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "not-email", "age": 30}'

# 422 — not a valid email address
```

### Combining Path, Query, and Body

```python
@app.put("/users/{user_id}")
async def update_user(
    user_id: int,                    # Path parameter
    notify: bool = False,            # Query parameter
    user: UserCreate = ...,          # Request body (... means required)
):
    return {
        "user_id": user_id,
        "notify": notify,
        "data": user.model_dump(),
    }
```

---

## 7.8 Response Models

Response models control what data is sent back to the client.

```python
class UserDB(BaseModel):
    id: int
    name: str
    email: str
    hashed_password: str        # Sensitive!
    created_at: datetime

class UserPublic(BaseModel):
    id: int
    name: str
    email: str
    created_at: datetime        # No password!

@app.get("/users/{user_id}", response_model=UserPublic)
async def get_user(user_id: int):
    # Even if your DB object has hashed_password,
    # FastAPI will filter it out based on UserPublic
    db_user = UserDB(
        id=user_id,
        name="Alice",
        email="alice@example.com",
        hashed_password="$2b$12$...",
        created_at=datetime.now(),
    )
    return db_user
    # Response will NOT include hashed_password
```

---

## 7.9 Dependency Injection

Dependencies are reusable components that FastAPI injects into your route handlers.

### Basic Dependency

```python
from fastapi import Depends

async def common_pagination(
    skip: int = 0,
    limit: int = 10,
) -> dict:
    return {"skip": skip, "limit": limit}

@app.get("/users")
async def list_users(pagination: dict = Depends(common_pagination)):
    return {"pagination": pagination, "users": []}

@app.get("/items")
async def list_items(pagination: dict = Depends(common_pagination)):
    return {"pagination": pagination, "items": []}
```

Both endpoints now accept `skip` and `limit` query parameters without duplicating the code.

### Authentication Dependency

```python
from fastapi import Depends, HTTPException, Header

async def get_current_user(authorization: str = Header()):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")

    token = authorization.removeprefix("Bearer ")

    # In reality, decode and verify the token here
    if token != "valid-token":
        raise HTTPException(status_code=401, detail="Invalid token")

    return {"user_id": 1, "name": "Alice"}

@app.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return user

@app.get("/my-orders")
async def get_my_orders(user: dict = Depends(get_current_user)):
    return {"user": user, "orders": []}
```

### Dependency Chains

Dependencies can depend on other dependencies:

```python
async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(db = Depends(get_db), token: str = Header()):
    user = db.query(User).filter(User.token == token).first()
    if not user:
        raise HTTPException(401, "Invalid token")
    return user

async def get_admin_user(user = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return user

@app.delete("/users/{user_id}")
async def delete_user(user_id: int, admin = Depends(get_admin_user)):
    # Only admins reach here
    return {"deleted": user_id}
```

---

## 7.10 Error Handling

### HTTPException

```python
from fastapi import HTTPException

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    if user_id > 100:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
    return {"id": user_id, "name": "Alice"}
```

### Custom Exception Handlers

```python
from fastapi import Request
from fastapi.responses import JSONResponse

class ItemNotFoundError(Exception):
    def __init__(self, item_id: int):
        self.item_id = item_id

@app.exception_handler(ItemNotFoundError)
async def item_not_found_handler(request: Request, exc: ItemNotFoundError):
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "ITEM_NOT_FOUND",
                "message": f"Item {exc.item_id} does not exist",
            }
        },
    )

@app.get("/items/{item_id}")
async def get_item(item_id: int):
    if item_id not in [1, 2, 3]:
        raise ItemNotFoundError(item_id)
    return {"id": item_id, "name": "Widget"}
```

---

## 7.11 Middleware

Middleware runs before every request and after every response.

```python
import time
from fastapi import Request

@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    response.headers["X-Process-Time"] = str(round(duration * 1000, 2))
    return response
```

```
Request flow:
  Client → Middleware → Route Handler → Middleware → Client
                │                            │
                └── Before request           └── After response
```

### Common Middleware Use Cases

- Request logging
- Timing/performance tracking
- Authentication (global)
- Request ID injection
- CORS (built-in)

---

## 7.12 CORS (Cross-Origin Resource Sharing)

When your frontend (localhost:3000) calls your API (localhost:8000), the browser blocks it by default. CORS headers tell the browser it's allowed.

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://myapp.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**In development:** `allow_origins=["*"]` allows everything (convenient but insecure).
**In production:** List specific allowed origins.

---

## 7.13 Background Tasks

For operations that don't need to complete before responding to the client.

```python
from fastapi import BackgroundTasks

def send_email(email: str, message: str):
    # Simulate slow email sending
    import time
    time.sleep(5)
    print(f"Email sent to {email}: {message}")

@app.post("/register")
async def register(
    email: str,
    background_tasks: BackgroundTasks,
):
    # Respond immediately
    background_tasks.add_task(send_email, email, "Welcome!")
    return {"message": "User registered. Welcome email will be sent."}
```

The client gets an immediate response. The email sends in the background.

---

## 7.14 Exercise: Build a Complete Notes API

Build a Notes API with these endpoints:

```
GET    /notes              → List all notes (with pagination)
POST   /notes              → Create a note
GET    /notes/{note_id}    → Get a single note
PATCH  /notes/{note_id}    → Update a note
DELETE /notes/{note_id}    → Delete a note
GET    /notes/search       → Search notes by title (query param)
```

Requirements:
- Use Pydantic models for request/response
- Validate that title is 1-200 characters
- Validate that content is max 10,000 characters
- Return 404 for nonexistent notes
- Use an in-memory list as "database" (for now)
- Include proper status codes
- Test using curl or the Swagger docs at `/docs`

---

## Checkpoint Quiz

1. What is ASGI? How does it relate to uvicorn and FastAPI?
2. What is the difference between a path parameter and a query parameter?
3. What does `response_model` do? Why is it important?
4. What is dependency injection in FastAPI? Give an example use case.
5. Why do you need CORS middleware?
6. What happens when you raise an `HTTPException`?
7. What is the purpose of middleware?
8. How does FastAPI generate API documentation?
9. When would you use background tasks?
10. What does `--reload` do in `uvicorn main:app --reload`?

---

## Common Mistakes

1. **Forgetting `async` for I/O handlers.** If your handler awaits something, it must be `async def`.
2. **Not using response_model.** Without it, you might accidentally expose sensitive data.
3. **Putting business logic in route handlers.** Keep handlers thin. Move logic to service functions.
4. **Not handling errors.** Every path through your code should return a proper response.
5. **Setting CORS to `*` in production.** This allows any website to call your API. Be specific.
6. **Not testing with the auto-generated docs.** `/docs` is your best development tool. Use it.
7. **Confusing `Depends()` syntax.** Pass the function itself: `Depends(get_user)`, not the result: `Depends(get_user())`.

---

## Next Module

Proceed to `08_building_real_apis.md` →
