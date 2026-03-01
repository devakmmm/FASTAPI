# Module 10: Authentication and Security

## Learning Objectives

By the end of this module, you will be able to:

- Explain the difference between authentication and authorization
- Implement password hashing with bcrypt
- Build JWT-based authentication
- Implement OAuth2 password flow with FastAPI
- Protect routes with authentication dependencies
- Implement role-based access control
- Configure CORS properly for production
- Avoid common security mistakes

---

## 10.1 Authentication vs Authorization

**Authentication** = Who are you? (Identity verification)
**Authorization** = What are you allowed to do? (Permission checking)

```
┌──────────────────────────────────────────────────────────┐
│                     Request arrives                       │
│                          │                                │
│               ┌──────────▼──────────┐                    │
│               │  AUTHENTICATION     │                    │
│               │  "Who is this?"     │                    │
│               │                     │                    │
│               │  Check token/       │                    │
│               │  credentials        │                    │
│               └──────────┬──────────┘                    │
│                    │           │                          │
│                  Valid      Invalid                       │
│                    │           │                          │
│                    │        401 Unauthorized              │
│                    ▼                                      │
│               ┌──────────────────────┐                   │
│               │  AUTHORIZATION       │                   │
│               │  "Is this allowed?"  │                   │
│               │                      │                   │
│               │  Check role/         │                   │
│               │  permissions         │                   │
│               └──────────┬───────────┘                   │
│                    │           │                          │
│                 Allowed     Denied                        │
│                    │           │                          │
│                    │        403 Forbidden                 │
│                    ▼                                      │
│               Process request                            │
└──────────────────────────────────────────────────────────┘
```

---

## 10.2 Password Hashing

**Never store plaintext passwords.** Ever. Not in a database. Not in a log. Not anywhere.

### How Hashing Works

```
Password: "mypassword123"
    │
    ▼ bcrypt hash
Hash: "$2b$12$LJ3m4ys3Lk..."  (60 characters, irreversible)
```

Properties of a good hash:
- **One-way**: Cannot reverse hash → password
- **Deterministic for verification**: Same password + same salt = same hash
- **Salted**: Each hash includes random data, so identical passwords produce different hashes
- **Slow on purpose**: bcrypt is intentionally slow to resist brute force

### Implementation

```bash
pip install passlib[bcrypt] python-jose[cryptography]
```

```python
# app/utils/security.py
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
```

```python
# Usage
hashed = hash_password("mypassword123")
print(hashed)
# $2b$12$LJ3m4ys3Lk.3/mIZRqMPFeL4sBmIb2RKOHh7rM7P0N7mNZz6IXa

assert verify_password("mypassword123", hashed) == True
assert verify_password("wrongpassword", hashed) == False
```

---

## 10.3 JWT (JSON Web Tokens)

JWT is a compact, self-contained way to transmit information between parties as a JSON object.

### Structure

```
eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkFsaWNlIn0.RJhE8IhR0M1...
│                      │                                                        │
└── Header             └── Payload                                              └── Signature
    (algorithm)            (claims/data)                                            (verification)
```

```
Header:  {"alg": "HS256", "typ": "JWT"}
Payload: {"sub": "user123", "exp": 1710000000, "role": "admin"}
Signature: HMAC-SHA256(header + "." + payload, SECRET_KEY)
```

### Key Properties

- **Self-contained**: The token carries the user info. No database lookup needed for every request.
- **Signed**: The server can verify it hasn't been tampered with.
- **Not encrypted**: Anyone can read the payload (base64 decode). Don't put secrets in it.
- **Expirable**: Tokens have an expiration time.

### Implementation

```python
# app/utils/security.py
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt

SECRET_KEY = "your-secret-key-change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
```

```python
# Usage
token = create_access_token({"sub": "alice", "role": "admin"})
print(token)
# eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

payload = decode_access_token(token)
print(payload)
# {"sub": "alice", "role": "admin", "exp": 1710000000}
```

---

## 10.4 OAuth2 Password Flow in FastAPI

FastAPI has built-in support for OAuth2.

### The Flow

```
1. Client sends username + password to /token
2. Server verifies credentials
3. Server returns JWT access token
4. Client sends token in Authorization header for subsequent requests
5. Server validates token on each request

┌──────────┐   POST /token          ┌──────────┐
│          │   {username, password}  │          │
│  Client  │ ─────────────────────► │  Server  │
│          │                        │          │
│          │ ◄───────────────────── │          │
│          │   {access_token, ...}  │          │
│          │                        │          │
│          │   GET /users/me        │          │
│          │   Authorization:       │          │
│          │   Bearer <token>       │          │
│          │ ─────────────────────► │          │
│          │                        │          │
│          │ ◄───────────────────── │          │
│          │   {id, username, ...}  │          │
└──────────┘                        └──────────┘
```

### Full Implementation

```python
# app/models.py — add auth models
from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool

    model_config = {"from_attributes": True}

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

```python
# app/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.db_models import User
from app.models import UserCreate, UserResponse, Token
from app.utils.security import (
    hash_password, verify_password,
    create_access_token, decode_access_token,
)

router = APIRouter(tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    result = await db.execute(
        select(User).where(
            (User.username == user_data.username) | (User.email == user_data.email)
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username or email already exists")

    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.username == form_data.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username})
    return Token(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
```

### Protecting Routes

```python
# app/routes/tasks.py — now requires authentication
from app.routes.auth import get_current_user
from app.db_models import User

@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(
    task: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # Auth required
):
    return await task_service.create_task(db, task, owner_id=current_user.id)
```

---

## 10.5 Role-Based Access Control (RBAC)

```python
# app/utils/security.py
from fastapi import Depends, HTTPException, status
from app.routes.auth import get_current_user
from app.db_models import User

def require_role(required_role: str):
    async def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required",
            )
        return current_user
    return role_checker

# Usage
@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    # Only admins can reach here
    await user_service.delete_user(db, user_id)
```

---

## 10.6 CORS in Production

```python
# Development (permissive)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Production (restrictive)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://myapp.com",
        "https://www.myapp.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)
```

---

## 10.7 Security Checklist

```
[ ] Passwords are hashed with bcrypt (never plaintext)
[ ] JWT secret key is loaded from environment variable
[ ] Tokens have expiration times
[ ] HTTPS is enforced in production
[ ] CORS is configured with specific origins
[ ] Rate limiting is implemented on login endpoint
[ ] Input validation on all endpoints (Pydantic)
[ ] SQL injection prevented (SQLAlchemy parameterized queries)
[ ] No sensitive data in JWT payload
[ ] No sensitive data in logs
[ ] No sensitive data in error responses
[ ] .env files are in .gitignore
[ ] Dependencies are kept up to date
[ ] Password requirements enforced (length, complexity)
```

---

## 10.8 Testing Authentication

```bash
# Register a user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com", "password": "secure123"}'

# Get a token (note: form data, not JSON — OAuth2 spec)
curl -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=alice&password=secure123"

# Response: {"access_token": "eyJ...", "token_type": "bearer"}

# Use the token
TOKEN="eyJ..."
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"

# Access a protected route
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Secure task"}'

# Try without token — should get 401
curl http://localhost:8000/api/v1/auth/me
```

---

## Checkpoint Quiz

1. What is the difference between authentication and authorization?
2. Why must passwords be hashed? Why is bcrypt used specifically?
3. What are the three parts of a JWT?
4. Why is JWT content not encrypted? Is that a problem?
5. What status code means "not authenticated"? What means "not authorized"?
6. What is the OAuth2 password flow?
7. Why does the `/token` endpoint use form data instead of JSON?
8. What happens when a JWT expires?
9. What does `Depends(get_current_user)` do in a route?
10. Why should CORS be restrictive in production?

---

## Common Mistakes

1. **Storing plaintext passwords.** Use bcrypt. Always.
2. **Hardcoding the JWT secret key.** Use environment variables.
3. **Not setting token expiration.** Tokens should expire. 15-60 minutes for access tokens.
4. **Putting sensitive data in JWT payload.** The payload is readable by anyone. No passwords, no credit cards.
5. **Not validating token on every request.** Every protected route must check the token.
6. **Using `GET` for login.** Login credentials go in the request body, never the URL.
7. **Returning different error messages for "user not found" vs "wrong password."** This leaks information about which usernames exist. Return the same error for both.
8. **Allowing unlimited login attempts.** Implement rate limiting on `/token`.

---

## Exercise: Complete Auth System

Build the full authentication system for the Task Manager:

1. User registration with password validation
2. Login with JWT token
3. Protected task CRUD (users can only see/edit their own tasks)
4. Admin role that can see all tasks
5. Token refresh endpoint
6. Change password endpoint

---

## Next Module

Proceed to `11_testing_and_debugging.md` →
