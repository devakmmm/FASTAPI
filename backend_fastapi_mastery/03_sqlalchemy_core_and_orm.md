# File: backend_fastapi_mastery/03_sqlalchemy_core_and_orm.md

# SQLAlchemy Core and ORM Mastery

## Why SQLAlchemy Matters

SQLAlchemy is the most mature and powerful database toolkit for Python. Understanding it deeply is essential for any backend engineer because:

1. **It abstracts SQL without hiding it** - You can always see what SQL is generated
2. **It handles connection pooling** - Critical for production performance
3. **It manages transactions properly** - Prevents data corruption
4. **It maps objects to tables** - Reduces boilerplate
5. **It's database agnostic** - Switch databases without code changes

**Two layers:**
- **Core**: SQL expression language, direct SQL generation
- **ORM**: Object-Relational Mapping, work with Python objects

---

## The Engine: Your Database Connection Factory

### What is the Engine?

The Engine is **not** a single connection. It's a **connection factory** that manages a **connection pool**.

```python
from sqlalchemy import create_engine

# Create engine (doesn't connect yet!)
engine = create_engine(
    "postgresql://user:password@localhost:5432/mydb",
    pool_size=5,           # Connections to keep open
    max_overflow=10,       # Extra connections when pool is full
    pool_timeout=30,       # Wait time for connection from pool
    pool_recycle=1800,     # Recycle connections after 30 min
    echo=False,            # Set True to log all SQL
)
```

### Connection Pool Explained

```
┌──────────────────────────────────────────────────────┐
│                       Engine                          │
│  ┌────────────────────────────────────────────────┐  │
│  │              Connection Pool                    │  │
│  │                                                 │  │
│  │   ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐    │  │
│  │   │Conn1│ │Conn2│ │Conn3│ │Conn4│ │Conn5│    │  │
│  │   └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘    │  │
│  │      │       │       │       │       │        │  │
│  └──────┼───────┼───────┼───────┼───────┼────────┘  │
└─────────┼───────┼───────┼───────┼───────┼────────────┘
          │       │       │       │       │
          ▼       ▼       ▼       ▼       ▼
     ┌─────────────────────────────────────────────┐
     │              PostgreSQL Database             │
     └─────────────────────────────────────────────┘
```

### Async Engine (For FastAPI)

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Async engine requires async driver
async_engine = create_async_engine(
    "postgresql+asyncpg://user:password@localhost:5432/mydb",
    pool_size=5,
    max_overflow=10,
    echo=False,
)

# Async session factory
AsyncSessionLocal = sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Important for FastAPI!
)
```

### Why `expire_on_commit=False` Matters

```python
# Default behavior: expire_on_commit=True
async with AsyncSessionLocal() as session:
    user = await session.get(User, 1)
    await session.commit()
    
    # PROBLEM: After commit, user attributes are expired
    # Accessing them triggers a new query
    print(user.name)  # ERROR! Session is closed, can't lazy load

# With expire_on_commit=False
async with AsyncSessionLocal() as session:
    user = await session.get(User, 1)
    await session.commit()
    
    # user attributes are still accessible
    print(user.name)  # Works!
    # But data might be stale if another process modified it
```

---

## Session Lifecycle

### What is a Session?

A Session is your **unit of work container**. It:
- Tracks all objects you load/create
- Batches changes for efficiency
- Manages transactions
- Ensures consistency

### Session States

Objects in a session have states:

```
┌─────────────┐
│  Transient  │  Object created, not attached to session
└──────┬──────┘
       │ session.add(obj)
       ▼
┌─────────────┐
│   Pending   │  Added to session, not yet in database
└──────┬──────┘
       │ session.flush() or session.commit()
       ▼
┌─────────────┐
│ Persistent  │  In session and in database
└──────┬──────┘
       │ session.expunge(obj) or session.close()
       ▼
┌─────────────┐
│  Detached   │  Was in session, now disconnected
└─────────────┘
```

### The FastAPI Session Pattern

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()  # Commit if no exception
        except Exception:
            await session.rollback()  # Rollback on error
            raise
        finally:
            await session.close()

@app.get("/users/{user_id}")
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
```

### Session Anti-Patterns

```python
# WRONG: Shared session across requests
db = AsyncSessionLocal()  # Global session

@app.get("/users")
async def get_users():
    return await db.query(User).all()  # Concurrent requests conflict!

# WRONG: Not handling session lifecycle
@app.get("/users")
async def get_users():
    session = AsyncSessionLocal()
    users = await session.query(User).all()
    # Session never closed! Connection leak!
    return users

# WRONG: Manual session without try/finally
@app.post("/users")
async def create_user(user: UserCreate):
    session = AsyncSessionLocal()
    new_user = User(**user.dict())
    session.add(new_user)
    await session.commit()  # If this fails, session stays open
    return new_user
```

---

## Unit of Work Pattern

SQLAlchemy implements the **Unit of Work** pattern:

1. Load objects into session
2. Modify objects (SQLAlchemy tracks changes)
3. Commit all changes atomically

```python
async def transfer_money(from_account_id: int, to_account_id: int, amount: Decimal):
    async with AsyncSessionLocal() as session:
        # Load both accounts
        from_account = await session.get(Account, from_account_id)
        to_account = await session.get(Account, to_account_id)
        
        # Modify objects (tracked automatically)
        from_account.balance -= amount
        to_account.balance += amount
        
        # Single commit = atomic transaction
        await session.commit()
        # Either both changes commit or neither does
```

### Flush vs Commit

```python
async with AsyncSessionLocal() as session:
    user = User(name="John")
    session.add(user)
    
    # flush: Write to database, don't end transaction
    await session.flush()
    print(user.id)  # ID is now available
    
    # More operations in same transaction...
    order = Order(user_id=user.id)
    session.add(order)
    
    # commit: End transaction, make changes permanent
    await session.commit()
```

**When to use flush:**
- Need generated IDs before commit
- Need to check database constraints
- Complex operations that reference new objects

---

## Transaction Management

### Implicit Transactions

SQLAlchemy starts transactions automatically:

```python
async with AsyncSessionLocal() as session:
    # Transaction starts on first operation
    user = await session.get(User, 1)
    user.name = "Updated"
    
    # Transaction commits here
    await session.commit()
```

### Explicit Transaction Control

```python
from sqlalchemy import text

async with AsyncSessionLocal() as session:
    async with session.begin():  # Explicit transaction
        await session.execute(text("UPDATE users SET active = false"))
        await session.execute(text("DELETE FROM sessions"))
        # Commits automatically at end of context
        # Rolls back if exception raised
```

### Savepoints (Nested Transactions)

```python
async with AsyncSessionLocal() as session:
    async with session.begin():
        user = User(name="John")
        session.add(user)
        await session.flush()
        
        try:
            async with session.begin_nested():  # Savepoint
                # Try something risky
                order = Order(user_id=user.id, total=-100)
                session.add(order)
                await session.flush()  # Might fail constraint
        except IntegrityError:
            # Savepoint rolled back, but user still exists
            pass
        
        # Outer transaction continues
        await session.commit()  # User committed, order not
```

### Transaction Isolation Levels

```python
from sqlalchemy import create_engine

# Set at engine level
engine = create_engine(
    DATABASE_URL,
    isolation_level="REPEATABLE READ"  # PostgreSQL
)

# Or per-session
async with AsyncSessionLocal() as session:
    await session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
```

| Level | Dirty Reads | Non-Repeatable Reads | Phantom Reads |
|-------|-------------|---------------------|---------------|
| READ UNCOMMITTED | Yes | Yes | Yes |
| READ COMMITTED | No | Yes | Yes |
| REPEATABLE READ | No | No | Yes (Postgres: No) |
| SERIALIZABLE | No | No | No |

---

## ORM Model Definition

### Basic Model

```python
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    orders = relationship("Order", back_populates="user", lazy="selectin")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"
```

### Modern Approach: Mapped Columns (SQLAlchemy 2.0)

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey
from datetime import datetime
from typing import Optional, List

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    # Type hints drive column types
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    
    # Optional field
    bio: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Relationship with type hint
    orders: Mapped[List["Order"]] = relationship(back_populates="user")
```

### Relationship Patterns

**One-to-Many:**

```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # One user has many orders
    orders: Mapped[List["Order"]] = relationship(back_populates="user")

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    
    # Many orders belong to one user
    user: Mapped["User"] = relationship(back_populates="orders")
```

**Many-to-Many:**

```python
# Association table
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    
    roles: Mapped[List["Role"]] = relationship(
        secondary=user_roles,
        back_populates="users"
    )

class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    
    users: Mapped[List["User"]] = relationship(
        secondary=user_roles,
        back_populates="roles"
    )
```

**Self-Referential (Tree Structure):**

```python
class Category(Base):
    __tablename__ = "categories"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id"),
        nullable=True
    )
    
    # Self-referential relationship
    children: Mapped[List["Category"]] = relationship(
        back_populates="parent",
        remote_side=[id]
    )
    parent: Mapped[Optional["Category"]] = relationship(
        back_populates="children",
        remote_side=[parent_id]
    )
```

---

## Lazy vs Eager Loading

### The N+1 Problem

```python
# The classic N+1 problem
async with AsyncSessionLocal() as session:
    # 1 query to get users
    result = await session.execute(select(User))
    users = result.scalars().all()
    
    for user in users:
        # N queries to get each user's orders!
        print(user.orders)  # Triggers lazy load for each user
```

### Loading Strategies

**Lazy Loading (Default):**
```python
class User(Base):
    orders: Mapped[List["Order"]] = relationship(
        lazy="select"  # Default - load when accessed
    )
```

**Select-In Loading:**
```python
class User(Base):
    orders: Mapped[List["Order"]] = relationship(
        lazy="selectin"  # Second query with IN clause
    )

# Generates:
# SELECT * FROM users
# SELECT * FROM orders WHERE user_id IN (1, 2, 3, 4, 5)
```

**Joined Loading:**
```python
class User(Base):
    orders: Mapped[List["Order"]] = relationship(
        lazy="joined"  # Single query with JOIN
    )

# Generates:
# SELECT * FROM users LEFT JOIN orders ON users.id = orders.user_id
```

### Query-Time Loading Options

```python
from sqlalchemy.orm import selectinload, joinedload, lazyload

# Override relationship loading for specific query
result = await session.execute(
    select(User)
    .options(selectinload(User.orders))
    .where(User.is_active == True)
)

# Nested eager loading
result = await session.execute(
    select(User)
    .options(
        selectinload(User.orders)
        .selectinload(Order.items)
    )
)

# Mixed strategies
result = await session.execute(
    select(User)
    .options(
        joinedload(User.profile),      # One-to-one: use join
        selectinload(User.orders)       # One-to-many: use select-in
    )
)
```

### When to Use Which

| Strategy | Best For | Avoid When |
|----------|----------|------------|
| `lazy="select"` | Rarely accessed relationships | Always accessing relationship |
| `lazy="selectin"` | Collections, multiple objects | Deep nesting |
| `lazy="joined"` | Single objects, one-to-one | Large collections, many columns |
| `lazy="subquery"` | Legacy, complex scenarios | Modern apps (use selectin) |

---

## Query Patterns

### Basic Queries (SQLAlchemy 2.0 Style)

```python
from sqlalchemy import select, and_, or_, func

# Get one by ID
user = await session.get(User, 1)

# Get one by condition
result = await session.execute(
    select(User).where(User.email == "test@example.com")
)
user = result.scalar_one_or_none()

# Get all with filter
result = await session.execute(
    select(User).where(User.is_active == True)
)
users = result.scalars().all()

# Complex conditions
result = await session.execute(
    select(User).where(
        and_(
            User.is_active == True,
            or_(
                User.role == "admin",
                User.department == "engineering"
            )
        )
    )
)
```

### Ordering and Pagination

```python
from sqlalchemy import desc

# Order by
result = await session.execute(
    select(User)
    .order_by(desc(User.created_at))
)

# Pagination
result = await session.execute(
    select(User)
    .order_by(User.id)
    .offset(20)
    .limit(10)
)
users = result.scalars().all()
```

### Aggregations

```python
from sqlalchemy import func

# Count
result = await session.execute(
    select(func.count()).select_from(User).where(User.is_active == True)
)
count = result.scalar()

# Group by
result = await session.execute(
    select(User.department, func.count(User.id))
    .group_by(User.department)
)
department_counts = result.all()  # [('engineering', 10), ('sales', 5)]

# Aggregations with having
result = await session.execute(
    select(User.department, func.count(User.id).label("count"))
    .group_by(User.department)
    .having(func.count(User.id) > 5)
)
```

### Joins

```python
# Implicit join (relationship-based)
result = await session.execute(
    select(User)
    .options(selectinload(User.orders))
    .where(User.id == 1)
)

# Explicit join
result = await session.execute(
    select(User, Order)
    .join(Order, User.id == Order.user_id)
    .where(Order.total > 100)
)

# Left outer join
result = await session.execute(
    select(User, Order)
    .outerjoin(Order, User.id == Order.user_id)
)

# Join with aggregation
result = await session.execute(
    select(User, func.sum(Order.total).label("total_spent"))
    .outerjoin(Order)
    .group_by(User.id)
)
```

### Subqueries

```python
# Subquery for filtering
active_order_users = (
    select(Order.user_id)
    .where(Order.status == "active")
    .distinct()
    .subquery()
)

result = await session.execute(
    select(User).where(User.id.in_(select(active_order_users.c.user_id)))
)

# Correlated subquery
latest_order = (
    select(func.max(Order.created_at))
    .where(Order.user_id == User.id)
    .correlate(User)
    .scalar_subquery()
)

result = await session.execute(
    select(User, latest_order.label("last_order_date"))
)
```

---

## Common ORM Mistakes

### 1. Detached Object Access

```python
# WRONG
async def get_user(user_id: int) -> User:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        return user  # User is now detached!

user = await get_user(1)
print(user.orders)  # ERROR: Detached instance, can't lazy load

# RIGHT: Eager load what you need
async def get_user_with_orders(user_id: int) -> User:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User)
            .options(selectinload(User.orders))
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        return user

# Or convert to Pydantic before returning
async def get_user(user_id: int) -> UserResponse:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        return UserResponse.model_validate(user)
```

### 2. Session Scope Issues

```python
# WRONG: Session per application
db = AsyncSessionLocal()

@app.get("/users")
async def get_users():
    # Multiple requests share session = data corruption
    return await db.query(User).all()

# WRONG: Session created but never closed
@app.get("/users")
async def get_users():
    session = AsyncSessionLocal()
    users = await session.query(User).all()
    return users  # Session leak!

# RIGHT: Session per request with proper cleanup
@app.get("/users")
async def get_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    return result.scalars().all()
```

### 3. N+1 in Loops

```python
# WRONG: N+1 queries
async with AsyncSessionLocal() as session:
    result = await session.execute(select(User))
    users = result.scalars().all()
    
    data = []
    for user in users:
        data.append({
            "user": user.name,
            "order_count": len(user.orders)  # N queries!
        })

# RIGHT: Eager load or aggregate in query
async with AsyncSessionLocal() as session:
    result = await session.execute(
        select(User, func.count(Order.id).label("order_count"))
        .outerjoin(Order)
        .group_by(User.id)
    )
    data = [
        {"user": row.User.name, "order_count": row.order_count}
        for row in result.all()
    ]
```

### 4. Not Using Indexes

```python
# Model without indexes = slow queries
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))  # No index!
    status: Mapped[str] = mapped_column(String(50))  # No index!

# Queries on email/status will be slow table scans

# RIGHT: Index frequently queried columns
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    
    # Composite index for common query patterns
    __table_args__ = (
        Index("ix_user_status_created", "status", "created_at"),
    )
```

### 5. Committing in Loops

```python
# WRONG: Commit per item = slow, no atomicity
async with AsyncSessionLocal() as session:
    for item_data in items:
        item = Item(**item_data)
        session.add(item)
        await session.commit()  # N commits!

# RIGHT: Bulk operations
async with AsyncSessionLocal() as session:
    items = [Item(**data) for data in items_data]
    session.add_all(items)
    await session.commit()  # Single commit
```

---

## Performance Patterns

### Bulk Insert

```python
from sqlalchemy import insert

# For thousands of rows
async with AsyncSessionLocal() as session:
    # Method 1: add_all (tracks objects, slower)
    users = [User(name=f"User {i}") for i in range(1000)]
    session.add_all(users)
    await session.commit()
    
    # Method 2: bulk_insert_mappings (no tracking, faster)
    await session.execute(
        insert(User),
        [{"name": f"User {i}"} for i in range(1000)]
    )
    await session.commit()
```

### Bulk Update

```python
from sqlalchemy import update

# Update without loading objects
async with AsyncSessionLocal() as session:
    await session.execute(
        update(User)
        .where(User.last_login < days_ago(30))
        .values(is_active=False)
    )
    await session.commit()
```

### Read Replicas

```python
# Production pattern: separate engines for read/write
write_engine = create_async_engine(PRIMARY_DB_URL)
read_engine = create_async_engine(REPLICA_DB_URL)

WriteSession = sessionmaker(write_engine, class_=AsyncSession)
ReadSession = sessionmaker(read_engine, class_=AsyncSession)

async def get_write_db():
    async with WriteSession() as session:
        yield session

async def get_read_db():
    async with ReadSession() as session:
        yield session

@app.post("/users")
async def create_user(user: UserCreate, db = Depends(get_write_db)):
    # Writes go to primary
    pass

@app.get("/users")
async def list_users(db = Depends(get_read_db)):
    # Reads go to replica
    pass
```

---

## Testing with SQLAlchemy

### In-Memory SQLite for Tests

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def db():
    # In-memory SQLite for fast tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()
    Base.metadata.drop_all(engine)

def test_create_user(db):
    user = User(name="Test", email="test@test.com")
    db.add(user)
    db.commit()
    
    assert user.id is not None
    assert db.query(User).count() == 1
```

### Test Database Transactions

```python
@pytest.fixture
def db():
    """Each test runs in a transaction that's rolled back"""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()
```

---

## Mastery Checkpoints

### Conceptual Questions

1. **What's the difference between `session.flush()` and `session.commit()`?**

   *Answer*: `flush()` writes pending changes to the database but doesn't end the transaction - changes are visible within the session but not committed. `commit()` ends the transaction, making changes permanent and visible to other connections. Use `flush()` when you need generated IDs or want to check constraints before committing.

2. **Why does the N+1 problem occur and how do you prevent it?**

   *Answer*: N+1 occurs when you load a list of objects (1 query) then access a lazy-loaded relationship on each (N queries). Prevent with eager loading: `selectinload` for collections (batches into IN query), `joinedload` for single objects (adds JOIN). Choose strategy based on data shape and query pattern.

3. **Explain the difference between `lazy="selectin"` and `lazy="joined"`**

   *Answer*: `selectin` issues a second query with `WHERE id IN (...)` for related objects - good for collections, avoids cartesian explosion. `joined` adds a LEFT JOIN to the main query - good for single objects, but with collections causes row multiplication. `selectin` is usually better for one-to-many, `joined` for one-to-one.

4. **What happens when you access a relationship on a detached object?**

   *Answer*: `DetachedInstanceError` if the relationship wasn't loaded. A detached object is no longer associated with a session, so it can't lazy load relationships. Solutions: eager load before detaching, use `expire_on_commit=False`, or convert to Pydantic model while session is open.

5. **Why set `expire_on_commit=False` for FastAPI sessions?**

   *Answer*: After commit, SQLAlchemy expires all objects, meaning the next attribute access triggers a refresh query. With FastAPI, we often return ORM objects after committing - if they're expired and the session context has ended, we can't access attributes. `expire_on_commit=False` keeps attributes accessible but data might be stale.

### Scenario Questions

6. **Design the ORM models for a blog with users, posts, comments, and tags (many-to-many).**

   *Answer*:
   ```python
   post_tags = Table(
       "post_tags",
       Base.metadata,
       Column("post_id", ForeignKey("posts.id"), primary_key=True),
       Column("tag_id", ForeignKey("tags.id"), primary_key=True),
   )
   
   class User(Base):
       __tablename__ = "users"
       id: Mapped[int] = mapped_column(primary_key=True)
       username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
       posts: Mapped[List["Post"]] = relationship(back_populates="author")
       comments: Mapped[List["Comment"]] = relationship(back_populates="author")
   
   class Post(Base):
       __tablename__ = "posts"
       id: Mapped[int] = mapped_column(primary_key=True)
       title: Mapped[str] = mapped_column(String(200))
       content: Mapped[str] = mapped_column(Text)
       author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
       author: Mapped["User"] = relationship(back_populates="posts")
       comments: Mapped[List["Comment"]] = relationship(back_populates="post")
       tags: Mapped[List["Tag"]] = relationship(secondary=post_tags, back_populates="posts")
   
   class Comment(Base):
       __tablename__ = "comments"
       id: Mapped[int] = mapped_column(primary_key=True)
       content: Mapped[str] = mapped_column(Text)
       post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
       author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
       post: Mapped["Post"] = relationship(back_populates="comments")
       author: Mapped["User"] = relationship(back_populates="comments")
   
   class Tag(Base):
       __tablename__ = "tags"
       id: Mapped[int] = mapped_column(primary_key=True)
       name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
       posts: Mapped[List["Post"]] = relationship(secondary=post_tags, back_populates="tags")
   ```

7. **You need to load a user with their 3 most recent orders. How?**

   *Answer*:
   ```python
   # Option 1: Subquery for filtering
   recent_orders = (
       select(Order)
       .where(Order.user_id == user_id)
       .order_by(desc(Order.created_at))
       .limit(3)
       .subquery()
   )
   
   result = await session.execute(
       select(User, recent_orders)
       .outerjoin(recent_orders, User.id == recent_orders.c.user_id)
       .where(User.id == user_id)
   )
   
   # Option 2: Two queries (often clearer)
   user = await session.get(User, user_id)
   recent_orders = await session.execute(
       select(Order)
       .where(Order.user_id == user_id)
       .order_by(desc(Order.created_at))
       .limit(3)
   )
   user.recent_orders = recent_orders.scalars().all()
   ```

8. **How do you handle soft deletes with SQLAlchemy?**

   *Answer*:
   ```python
   class SoftDeleteMixin:
       deleted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
       
       @property
       def is_deleted(self) -> bool:
           return self.deleted_at is not None
   
   class User(Base, SoftDeleteMixin):
       __tablename__ = "users"
       id: Mapped[int] = mapped_column(primary_key=True)
   
   # Soft delete
   user.deleted_at = datetime.utcnow()
   await session.commit()
   
   # Query active records
   result = await session.execute(
       select(User).where(User.deleted_at.is_(None))
   )
   
   # Or use event listeners to filter automatically
   @event.listens_for(Session, "do_orm_execute")
   def filter_soft_deleted(execute_state):
       if execute_state.is_select:
           execute_state.statement = execute_state.statement.where(
               User.deleted_at.is_(None)
           )
   ```

9. **Your query is slow. How do you debug it?**

   *Answer*:
   ```python
   # 1. Enable SQL logging
   engine = create_engine(URL, echo=True)
   
   # 2. Get the compiled SQL
   query = select(User).where(User.is_active == True)
   print(query.compile(compile_kwargs={"literal_binds": True}))
   
   # 3. Use EXPLAIN ANALYZE (PostgreSQL)
   result = await session.execute(
       text("EXPLAIN ANALYZE " + str(query.compile(compile_kwargs={"literal_binds": True})))
   )
   print(result.fetchall())
   
   # 4. Check for N+1 - count queries per request
   # 5. Check indexes - missing indexes on WHERE/JOIN columns
   # 6. Check data volume - consider pagination
   # 7. Check eager loading - maybe loading too much
   ```

10. **How do you implement optimistic locking?**

    *Answer*:
    ```python
    class Order(Base):
        __tablename__ = "orders"
        id: Mapped[int] = mapped_column(primary_key=True)
        version: Mapped[int] = mapped_column(default=1)
        total: Mapped[Decimal]
        
        __mapper_args__ = {
            "version_id_col": version
        }
    
    # SQLAlchemy automatically includes version in UPDATE WHERE clause
    # If version doesn't match, StaleDataError is raised
    
    async def update_order(order_id: int, new_total: Decimal):
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, order_id)
            order.total = new_total
            try:
                await session.commit()  # Includes WHERE version = X
            except StaleDataError:
                # Another process modified the order
                raise HTTPException(409, "Order was modified by another process")
    ```

---

## Interview Framing

When discussing SQLAlchemy in interviews:

1. **Show understanding of connection pooling**: "The engine manages a pool of connections. I configure pool_size based on expected concurrency and database limits. For Kubernetes with multiple replicas, I ensure total connections across pods don't exceed database max_connections."

2. **Explain session lifecycle clearly**: "I use request-scoped sessions with dependency injection. Each request gets a fresh session, changes are committed at the end, and the session is closed. This prevents data leaking between requests."

3. **Discuss eager loading strategy**: "I default to lazy loading but analyze query patterns. For APIs that always need related data, I use selectinload for collections and joinedload for single objects. I watch for N+1 in logs."

4. **Connect to production concerns**: "I set echo=True in development to see generated SQL. In production, I monitor slow queries, check for missing indexes, and use read replicas for read-heavy endpoints."

5. **Show transaction awareness**: "I understand that reads can see uncommitted writes within the same transaction. For complex operations, I use explicit transaction boundaries and savepoints for partial rollback."
