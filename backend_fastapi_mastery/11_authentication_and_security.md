# File: backend_fastapi_mastery/11_authentication_and_security.md

# Authentication and Security

## Authentication vs Authorization

**Authentication (AuthN)**: "Who are you?"
- Verifying identity
- Login with credentials
- Token validation

**Authorization (AuthZ)**: "What can you do?"
- Permission checking
- Role-based access
- Resource ownership

```python
# Authentication: Verify the user
current_user = await authenticate(token)  # Who is this?

# Authorization: Check permissions
if not current_user.can_delete(resource):  # Can they do this?
    raise HTTPException(403, "Not authorized")
```

---

## OAuth2 with JWT in FastAPI

### JWT Structure

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.Gfx6VO9tcxwk6xqx9yYzSfebfeakZp5JYIgP_edcw_A

Header.Payload.Signature

Header: {"alg": "HS256", "typ": "JWT"}
Payload: {"sub": "1234567890", "name": "John", "exp": 1234567890}
Signature: HMACSHA256(base64(header) + "." + base64(payload), secret)
```

### Complete JWT Authentication

```python
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

# Configuration
SECRET_KEY = "your-secret-key-min-32-characters-long"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenPayload(BaseModel):
    sub: str  # User ID
    exp: datetime
    type: str  # "access" or "refresh"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenPayload(**payload)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )
```

### Authentication Routes

```python
@app.post("/auth/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """OAuth2 compatible token login"""
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return Token(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id)
    )

@app.post("/auth/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    """Get new access token using refresh token"""
    payload = decode_token(refresh_token)
    
    if payload.type != "refresh":
        raise HTTPException(400, "Invalid token type")
    
    user = await db.get(User, int(payload.sub))
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    
    return Token(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id)
    )
```

### Current User Dependencies

```python
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user"""
    payload = decode_token(token)
    
    if payload.type != "access":
        raise HTTPException(401, "Invalid token type")
    
    user = await db.get(User, int(payload.sub))
    if not user:
        raise HTTPException(401, "User not found")
    
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(403, "Inactive user")
    return current_user

async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Get current admin user"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    return current_user

# Usage in routes
@app.get("/users/me")
async def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user

@app.get("/admin/users")
async def admin_list_users(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    return await db.query(User).all()
```

---

## Role-Based Access Control (RBAC)

### Permission System

```python
from enum import Enum
from typing import Set

class Permission(str, Enum):
    # User permissions
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"
    
    # Order permissions
    ORDER_READ = "order:read"
    ORDER_WRITE = "order:write"
    ORDER_DELETE = "order:delete"
    
    # Admin permissions
    ADMIN_ACCESS = "admin:access"

class Role(str, Enum):
    USER = "user"
    MANAGER = "manager"
    ADMIN = "admin"

ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.USER: {
        Permission.USER_READ,
        Permission.ORDER_READ,
        Permission.ORDER_WRITE,
    },
    Role.MANAGER: {
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.ORDER_READ,
        Permission.ORDER_WRITE,
        Permission.ORDER_DELETE,
    },
    Role.ADMIN: {
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_DELETE,
        Permission.ORDER_READ,
        Permission.ORDER_WRITE,
        Permission.ORDER_DELETE,
        Permission.ADMIN_ACCESS,
    },
}

def has_permission(user: User, permission: Permission) -> bool:
    user_permissions = ROLE_PERMISSIONS.get(user.role, set())
    return permission in user_permissions
```

### Permission Dependencies

```python
from functools import wraps

def require_permission(permission: Permission):
    """Dependency that checks for specific permission"""
    async def permission_checker(
        current_user: User = Depends(get_current_active_user)
    ) -> User:
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {permission.value}"
            )
        return current_user
    return permission_checker

# Usage
@app.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_permission(Permission.USER_DELETE)),
    db: AsyncSession = Depends(get_db)
):
    await db.delete(User, user_id)
    return {"deleted": True}

@app.get("/admin/dashboard")
async def admin_dashboard(
    current_user: User = Depends(require_permission(Permission.ADMIN_ACCESS))
):
    return {"admin": "data"}
```

### Resource-Based Authorization

```python
async def get_order_with_access(
    order_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Order:
    """Get order, checking that user has access"""
    order = await db.get(Order, order_id)
    
    if not order:
        raise HTTPException(404, "Order not found")
    
    # Admin can access any order
    if current_user.is_admin:
        return order
    
    # Users can only access their own orders
    if order.user_id != current_user.id:
        raise HTTPException(403, "Access denied to this order")
    
    return order

@app.get("/orders/{order_id}")
async def get_order(order: Order = Depends(get_order_with_access)):
    return order
```

---

## Rate Limiting

### Simple Rate Limiter

```python
import time
from collections import defaultdict
from fastapi import Request

class RateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests: dict[str, list[float]] = defaultdict(list)
    
    async def check(self, key: str) -> bool:
        """Returns True if request is allowed"""
        now = time.time()
        minute_ago = now - 60
        
        # Clean old requests
        self.requests[key] = [
            t for t in self.requests[key] if t > minute_ago
        ]
        
        if len(self.requests[key]) >= self.requests_per_minute:
            return False
        
        self.requests[key].append(now)
        return True

rate_limiter = RateLimiter(requests_per_minute=60)

async def rate_limit_dependency(request: Request):
    # Rate limit by IP or user
    key = request.client.host
    
    if not await rate_limiter.check(key):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"}
        )
```

### Redis-Based Rate Limiter (Production)

```python
import redis.asyncio as redis

class RedisRateLimiter:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: int = 60
    ) -> tuple[bool, int]:
        """
        Returns (is_allowed, remaining_requests)
        """
        redis_key = f"ratelimit:{key}"
        
        pipe = self.redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds)
        results = await pipe.execute()
        
        current_count = results[0]
        remaining = max(0, limit - current_count)
        
        return current_count <= limit, remaining
    
    async def get_reset_time(self, key: str) -> int:
        """Get TTL until rate limit resets"""
        ttl = await self.redis.ttl(f"ratelimit:{key}")
        return max(0, ttl)

# Tiered rate limits
RATE_LIMITS = {
    "anonymous": {"limit": 20, "window": 60},
    "authenticated": {"limit": 100, "window": 60},
    "premium": {"limit": 1000, "window": 60},
}

async def tiered_rate_limit(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user)
):
    if current_user:
        tier = "premium" if current_user.is_premium else "authenticated"
        key = f"user:{current_user.id}"
    else:
        tier = "anonymous"
        key = f"ip:{request.client.host}"
    
    config = RATE_LIMITS[tier]
    allowed, remaining = await rate_limiter.check(key, config["limit"], config["window"])
    
    if not allowed:
        reset_time = await rate_limiter.get_reset_time(key)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(config["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_time),
                "Retry-After": str(reset_time)
            }
        )
    
    # Add headers to response
    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(config["limit"]),
        "X-RateLimit-Remaining": str(remaining),
    }
```

---

## Security Headers Middleware

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Prevent XSS
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Content Security Policy
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        
        # HTTPS enforcement
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

---

## CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

# Development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Production
ALLOWED_ORIGINS = [
    "https://myapp.com",
    "https://admin.myapp.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

## Security Anti-Patterns

### 1. Storing Passwords in Plain Text

```python
# WRONG
user.password = password  # Plain text!

# RIGHT
user.password_hash = pwd_context.hash(password)
```

### 2. Exposing Sensitive Data in Responses

```python
# WRONG
@app.get("/users/{id}")
async def get_user(id: int, db = Depends(get_db)):
    return await db.get(User, id)  # Returns password_hash!

# RIGHT
class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    # No password_hash!

@app.get("/users/{id}", response_model=UserResponse)
async def get_user(id: int, db = Depends(get_db)):
    return await db.get(User, id)
```

### 3. SQL Injection

```python
# WRONG
query = f"SELECT * FROM users WHERE email = '{email}'"

# RIGHT
result = await db.execute(
    select(User).where(User.email == email)
)
```

### 4. Timing Attacks on Authentication

```python
# WRONG: Different timing reveals if user exists
async def authenticate(email: str, password: str):
    user = await db.query(User).filter_by(email=email).first()
    if not user:
        return None  # Fast return - attacker knows user doesn't exist
    
    if not verify_password(password, user.password_hash):
        return None
    
    return user

# RIGHT: Constant time regardless of user existence
DUMMY_HASH = pwd_context.hash("dummy-password")

async def authenticate(email: str, password: str):
    user = await db.query(User).filter_by(email=email).first()
    
    if user:
        password_valid = verify_password(password, user.password_hash)
    else:
        # Still do hash comparison to keep timing constant
        verify_password(password, DUMMY_HASH)
        password_valid = False
    
    if not password_valid:
        return None
    
    return user
```

### 5. Insecure Direct Object References (IDOR)

```python
# WRONG: No authorization check
@app.get("/orders/{order_id}")
async def get_order(order_id: int, db = Depends(get_db)):
    return await db.get(Order, order_id)  # Anyone can access any order!

# RIGHT: Check ownership
@app.get("/orders/{order_id}")
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(404)
    
    if order.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(403, "Access denied")
    
    return order
```

### 6. Missing Token Expiration

```python
# WRONG: Token never expires
token = jwt.encode({"sub": user_id}, SECRET_KEY)

# RIGHT: Always include expiration
token = jwt.encode({
    "sub": user_id,
    "exp": datetime.utcnow() + timedelta(minutes=30)
}, SECRET_KEY)
```

### 7. Logging Sensitive Data

```python
# WRONG
logger.info(f"User login: {email}, password: {password}")
logger.info(f"Payment: card_number={card_number}")

# RIGHT
logger.info(f"User login attempt: {email}")
logger.info(f"Payment processed for user {user_id}")
```

---

## Input Validation Security

```python
from pydantic import BaseModel, Field, validator
import re

class UserCreate(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=100)
    
    @validator("email")
    def validate_email(cls, v):
        # Use proper email validation
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, v):
            raise ValueError("Invalid email format")
        return v.lower()
    
    @validator("password")
    def validate_password(cls, v):
        if not re.search(r'[A-Z]', v):
            raise ValueError("Password must contain uppercase")
        if not re.search(r'[a-z]', v):
            raise ValueError("Password must contain lowercase")
        if not re.search(r'\d', v):
            raise ValueError("Password must contain digit")
        if not re.search(r'[!@#$%^&*]', v):
            raise ValueError("Password must contain special character")
        return v
    
    @validator("name")
    def sanitize_name(cls, v):
        # Remove potential XSS
        v = re.sub(r'[<>"\'/]', '', v)
        return v.strip()
```

---

## Mastery Checkpoints

### Conceptual Questions

1. **What's the difference between access tokens and refresh tokens?**

   *Answer*: Access tokens are short-lived (minutes), used to access resources. Refresh tokens are long-lived (days), used only to get new access tokens. This limits damage if access token is stolen while allowing persistent login. Access tokens are sent with every request; refresh tokens are only sent to the refresh endpoint.

2. **Why use bcrypt for password hashing instead of SHA256?**

   *Answer*: bcrypt is designed for password hashing: it's intentionally slow (work factor adjustable), includes salt automatically, and resists GPU/ASIC attacks. SHA256 is fast (bad for passwords - attackers can try billions per second) and doesn't include salt. Also consider argon2 for modern systems.

3. **What is a timing attack and how do you prevent it?**

   *Answer*: Timing attacks measure response time to deduce information. If checking "user exists?" is faster than "user exists + wrong password," attackers learn which users exist. Prevent by making authentication paths take constant time - always do password comparison even for non-existent users.

4. **Why should JWTs have expiration times?**

   *Answer*: If a JWT is stolen, it's valid until expiration. Without expiration, it's valid forever. Short expiration (15-30 min) limits the window of compromise. Refresh tokens allow getting new access tokens without re-login while maintaining security.

5. **What is IDOR and how do you prevent it?**

   *Answer*: Insecure Direct Object Reference - when users can access resources they shouldn't by changing IDs (e.g., /orders/123 → /orders/124). Prevent by always checking authorization: "Does this user own/have access to this resource?" Not just "Is this user authenticated?"

### Scenario Questions

6. **Design authentication for a mobile app that needs to stay logged in for weeks.**

   *Answer*:
   ```python
   # Token strategy
   ACCESS_TOKEN_EXPIRE = timedelta(minutes=15)  # Short
   REFRESH_TOKEN_EXPIRE = timedelta(days=30)    # Long
   
   # Login response
   return {
       "access_token": create_token(user.id, ACCESS_TOKEN_EXPIRE, "access"),
       "refresh_token": create_token(user.id, REFRESH_TOKEN_EXPIRE, "refresh")
   }
   
   # App workflow:
   # 1. Store both tokens securely (Keychain/Keystore)
   # 2. Use access token for API calls
   # 3. When access token expires (401), use refresh token to get new pair
   # 4. If refresh token expires, require re-login
   
   # Security: Refresh token rotation
   @app.post("/auth/refresh")
   async def refresh(refresh_token: str):
       payload = decode_token(refresh_token)
       
       # Invalidate old refresh token
       await redis.sadd(f"revoked_tokens", refresh_token)
       
       # Issue new pair
       return {
           "access_token": create_token(...),
           "refresh_token": create_token(...)  # New refresh token
       }
   ```

7. **How do you implement "logout from all devices"?**

   *Answer*:
   ```python
   # Add token version to user
   class User(Base):
       token_version: int = 1  # Increment to invalidate all tokens
   
   # Include version in token
   def create_token(user_id: int, version: int):
       return jwt.encode({
           "sub": user_id,
           "version": version,
           "exp": ...
       }, SECRET_KEY)
   
   # Check version on every request
   async def get_current_user(token: str = Depends(oauth2_scheme)):
       payload = decode_token(token)
       user = await db.get(User, payload["sub"])
       
       if user.token_version != payload["version"]:
           raise HTTPException(401, "Token invalidated")
       
       return user
   
   # Logout from all devices
   @app.post("/auth/logout-all")
   async def logout_all(current_user: User = Depends(get_current_user)):
       current_user.token_version += 1
       await db.commit()
       return {"status": "logged out from all devices"}
   ```

8. **You need to implement API key authentication for third-party integrations alongside JWT for users. How?**

   *Answer*:
   ```python
   from fastapi.security import APIKeyHeader
   
   api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
   oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)
   
   async def get_current_entity(
       api_key: str = Depends(api_key_header),
       token: str = Depends(oauth2_scheme),
       db: AsyncSession = Depends(get_db)
   ) -> User | APIClient:
       """Support both JWT and API key authentication"""
       
       if api_key:
           # API key authentication
           client = await db.query(APIClient).filter_by(
               key_hash=hash_api_key(api_key),
               is_active=True
           ).first()
           if not client:
               raise HTTPException(401, "Invalid API key")
           return client
       
       if token:
           # JWT authentication
           return await get_current_user(token, db)
       
       raise HTTPException(401, "Authentication required")
   ```

9. **How do you protect against brute force login attacks?**

   *Answer*:
   ```python
   async def login(email: str, password: str, request: Request):
       # Rate limit by IP
       ip = request.client.host
       ip_attempts = await redis.incr(f"login_attempts:ip:{ip}")
       await redis.expire(f"login_attempts:ip:{ip}", 3600)
       
       if ip_attempts > 20:
           raise HTTPException(429, "Too many attempts from this IP")
       
       # Rate limit by email
       email_attempts = await redis.incr(f"login_attempts:email:{email}")
       await redis.expire(f"login_attempts:email:{email}", 3600)
       
       if email_attempts > 5:
           raise HTTPException(429, "Too many attempts for this account")
       
       # Authenticate
       user = await authenticate(email, password)
       
       if user:
           # Clear attempt counters on success
           await redis.delete(f"login_attempts:email:{email}")
           return create_tokens(user)
       
       raise HTTPException(401, "Invalid credentials")
   ```

10. **Design permission system for a multi-tenant SaaS with organizations, teams, and projects.**

    *Answer*:
    ```python
    class Permission(str, Enum):
        VIEW = "view"
        EDIT = "edit"
        DELETE = "delete"
        ADMIN = "admin"
    
    class ResourceType(str, Enum):
        ORGANIZATION = "organization"
        TEAM = "team"
        PROJECT = "project"
    
    # User can have different roles in different contexts
    class RoleAssignment(Base):
        user_id: int
        resource_type: ResourceType
        resource_id: int
        role: str  # "owner", "admin", "member", "viewer"
    
    async def check_permission(
        user_id: int,
        resource_type: ResourceType,
        resource_id: int,
        permission: Permission
    ) -> bool:
        # Get user's role for this resource
        assignment = await db.query(RoleAssignment).filter_by(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id
        ).first()
        
        if not assignment:
            # Check parent resource (project → team → org)
            if resource_type == ResourceType.PROJECT:
                project = await db.get(Project, resource_id)
                return await check_permission(user_id, ResourceType.TEAM, project.team_id, permission)
            return False
        
        # Check if role has permission
        return ROLE_PERMISSIONS[assignment.role].get(permission, False)
    
    def require_resource_permission(resource_type: ResourceType, permission: Permission):
        async def checker(
            resource_id: int,
            current_user: User = Depends(get_current_user)
        ):
            if not await check_permission(current_user.id, resource_type, resource_id, permission):
                raise HTTPException(403, f"No {permission.value} permission")
        return checker
    ```

---

## Interview Framing

When discussing security:

1. **Show defense in depth**: "I implement security at multiple layers - authentication at the gateway, authorization in the service, input validation at the model level, and encryption at rest and in transit."

2. **Discuss specific vulnerabilities**: "I validate and sanitize all inputs to prevent injection attacks. I use parameterized queries, never string interpolation for SQL. I escape output to prevent XSS."

3. **Explain token strategy**: "I use short-lived access tokens with longer refresh tokens. This limits the window if a token is compromised while providing good UX. Refresh tokens are rotated on use."

4. **Connect to compliance**: "For PCI compliance, credit card data never touches our servers - we use tokenization. For GDPR, I implement data deletion endpoints and audit logging."

5. **Mention ongoing practices**: "Security isn't one-time. I keep dependencies updated, use security scanners in CI, and have processes for responding to vulnerabilities."
