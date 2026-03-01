# Module 09: Database Integration

## Learning Objectives

By the end of this module, you will be able to:

- Explain why APIs need databases (vs in-memory storage)
- Set up SQLite and PostgreSQL
- Use SQLAlchemy as an ORM with FastAPI
- Define database models and relationships
- Perform CRUD operations through the ORM
- Run database migrations with Alembic
- Understand the difference between sync and async database access
- Convert the Task Manager API to use a real database

---

## 9.1 Why Databases?

The in-memory dictionary from Module 08 has fatal flaws:

1. **Data lost on restart.** Kill the server → all data gone.
2. **No concurrency safety.** Multiple requests modifying the dict simultaneously → corruption.
3. **No querying.** Want tasks sorted by date, filtered by status, with full-text search? Write it yourself.
4. **No persistence.** Cannot back up, replicate, or scale.

Databases solve all of these. For APIs, you will almost always use a relational database (PostgreSQL, MySQL, SQLite).

---

## 9.2 SQLite vs PostgreSQL

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| Setup | Zero (file-based) | Requires server |
| Concurrency | Limited (file locks) | Excellent |
| Performance | Good for small apps | Production-grade |
| Features | Basic SQL | Advanced (JSON, full-text, etc.) |
| Use case | Development, prototyping | Production |

**Strategy:** Develop with SQLite. Deploy with PostgreSQL. SQLAlchemy abstracts the difference.

### Setup

```bash
# SQLite — already installed with Python
python3 -c "import sqlite3; print(sqlite3.sqlite_version)"

# PostgreSQL
# macOS:
brew install postgresql@16
brew services start postgresql@16

# Ubuntu:
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql

# Create a database
createdb taskmanager
# Or via psql:
psql -c "CREATE DATABASE taskmanager;"
```

---

## 9.3 SQLAlchemy — The ORM

An ORM (Object-Relational Mapper) maps Python classes to database tables.

```
Python Class  ←→  Database Table
Python Object ←→  Database Row
Attribute     ←→  Column
```

### Install

```bash
pip install sqlalchemy alembic
pip install aiosqlite        # Async SQLite driver
pip install asyncpg           # Async PostgreSQL driver (for production)
```

### Database Connection

```python
# app/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "sqlite+aiosqlite:///./taskmanager.db"
# For PostgreSQL:
# DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/taskmanager"

engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

---

## 9.4 Database Models

Database models define table structure. These are separate from Pydantic models.

```python
# app/db_models.py
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum

class TaskStatusDB(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"

class PriorityDB(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(
        SAEnum(PriorityDB), default=PriorityDB.medium, nullable=False
    )
    status: Mapped[str] = mapped_column(
        SAEnum(TaskStatusDB), default=TaskStatusDB.todo, nullable=False
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, title='{self.title}', status='{self.status}')>"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
```

### Pydantic Models vs SQLAlchemy Models

```
SQLAlchemy Model (db_models.py):
  - Defines table structure
  - Handles database operations
  - Maps to/from database rows

Pydantic Model (models.py):
  - Defines API request/response shapes
  - Handles validation
  - Handles serialization to/from JSON

They are SEPARATE. A common pattern:

  Request (JSON) → Pydantic Model → Service Logic → SQLAlchemy Model → Database
  Database → SQLAlchemy Model → Service Logic → Pydantic Model → Response (JSON)
```

---

## 9.5 CRUD with SQLAlchemy

### Create

```python
# app/services/task_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db_models import Task
from app.models import TaskCreate, TaskResponse

async def create_task(db: AsyncSession, data: TaskCreate) -> TaskResponse:
    task = Task(
        title=data.title,
        description=data.description,
        priority=data.priority,
        due_date=data.due_date,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return TaskResponse.model_validate(task, from_attributes=True)
```

### Read (Single)

```python
async def get_task(db: AsyncSession, task_id: int) -> TaskResponse:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskResponse.model_validate(task, from_attributes=True)
```

### Read (List with Filtering)

```python
from sqlalchemy import select, func

async def list_tasks(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    status: str | None = None,
    search: str | None = None,
) -> dict:
    query = select(Task)

    if status:
        query = query.where(Task.status == status)
    if search:
        query = query.where(Task.title.ilike(f"%{search}%"))

    query = query.order_by(Task.created_at.desc())

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    tasks = result.scalars().all()

    return {
        "data": [TaskResponse.model_validate(t, from_attributes=True) for t in tasks],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": math.ceil(total / per_page) if total > 0 else 1,
    }
```

### Update

```python
async def update_task(
    db: AsyncSession, task_id: int, data: TaskUpdate
) -> TaskResponse:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(task, key, value)

    await db.flush()
    await db.refresh(task)
    return TaskResponse.model_validate(task, from_attributes=True)
```

### Delete

```python
async def delete_task(db: AsyncSession, task_id: int) -> None:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    await db.delete(task)
```

---

## 9.6 Updating Routes to Use the Database

```python
# app/routes/tasks.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import TaskCreate, TaskUpdate, TaskResponse, TaskListResponse
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(task: TaskCreate, db: AsyncSession = Depends(get_db)):
    return await task_service.create_task(db, task)

@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await task_service.list_tasks(db, page, per_page, status, search)

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    return await task_service.get_task(db, task_id)

@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int, task: TaskUpdate, db: AsyncSession = Depends(get_db)
):
    return await task_service.update_task(db, task_id, task)

@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    await task_service.delete_task(db, task_id)
```

### Creating Tables on Startup

```python
# app/main.py
from contextlib import asynccontextmanager
from app.database import engine, Base

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Task Manager API", lifespan=lifespan)
```

---

## 9.7 Database Migrations with Alembic

Creating tables with `create_all` works for development. For production, you need migrations — versioned, incremental changes to the database schema.

### Setup

```bash
alembic init alembic
```

This creates:
```
alembic/
├── env.py           ← Migration environment config
├── versions/        ← Migration files go here
└── script.py.mako   ← Template for new migrations
alembic.ini          ← Alembic configuration
```

### Configure Alembic

```python
# alembic/env.py — key changes:
from app.database import Base
from app.db_models import Task, User  # Import all models

target_metadata = Base.metadata
```

```ini
# alembic.ini
sqlalchemy.url = sqlite:///./taskmanager.db
```

### Create and Run Migrations

```bash
# Generate a migration from model changes
alembic revision --autogenerate -m "create tasks and users tables"

# Apply migrations
alembic upgrade head

# See current version
alembic current

# See migration history
alembic history

# Downgrade one version
alembic downgrade -1

# Downgrade to beginning
alembic downgrade base
```

### Migration Workflow

```
1. Modify SQLAlchemy model (add column, change type, etc.)
2. Generate migration: alembic revision --autogenerate -m "description"
3. Review the generated migration file in alembic/versions/
4. Apply: alembic upgrade head
5. Commit the migration file to Git
```

**Always review auto-generated migrations.** They can miss things or generate incorrect operations.

---

## 9.8 Relationships

### One-to-Many: User has many Tasks

```python
# app/db_models.py
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    # ...

    tasks: Mapped[list["Task"]] = relationship(back_populates="owner")

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # ...

    owner: Mapped["User | None"] = relationship(back_populates="tasks")
```

### Querying with Relationships

```python
from sqlalchemy.orm import selectinload

# Get user with their tasks
result = await db.execute(
    select(User).where(User.id == user_id).options(selectinload(User.tasks))
)
user = result.scalar_one_or_none()
print(user.tasks)  # List of Task objects
```

### Many-to-Many: Tasks have many Tags

```python
from sqlalchemy import Table, Column, ForeignKey

task_tags = Table(
    "task_tags",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)

class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)

    tasks: Mapped[list["Task"]] = relationship(
        secondary=task_tags, back_populates="tags"
    )

class Task(Base):
    __tablename__ = "tasks"
    # ... other columns ...

    tags: Mapped[list["Tag"]] = relationship(
        secondary=task_tags, back_populates="tasks"
    )
```

---

## 9.9 Database Best Practices

### 1. Use Indexes

```python
from sqlalchemy import Index

class Task(Base):
    __tablename__ = "tasks"
    # ... columns ...

    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_owner_id", "owner_id"),
        Index("ix_tasks_created_at", "created_at"),
    )
```

### 2. Use Transactions

The `get_db` dependency wraps each request in a transaction. If the route succeeds, it commits. If it raises, it rolls back. This is automatic with the pattern shown above.

### 3. Avoid N+1 Queries

```python
# BAD: N+1 — one query per task to load owner
tasks = await db.execute(select(Task))
for task in tasks.scalars():
    print(task.owner.username)  # Each access triggers a query

# GOOD: Eager load
tasks = await db.execute(
    select(Task).options(selectinload(Task.owner))
)
for task in tasks.scalars():
    print(task.owner.username)  # Already loaded, no extra queries
```

### 4. Connection Pooling

SQLAlchemy handles this automatically. For production PostgreSQL:

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)
```

---

## Checkpoint Quiz

1. Why can't you use an in-memory dict in production?
2. What is an ORM? What does SQLAlchemy do?
3. What is the difference between a SQLAlchemy model and a Pydantic model?
4. What does `alembic revision --autogenerate` do?
5. What is the N+1 query problem?
6. Why use `exclude_unset=True` when updating?
7. What does `get_db` do as a FastAPI dependency?
8. When should you use SQLite vs PostgreSQL?
9. What is a database migration?
10. What does `selectinload` do?

---

## Common Mistakes

1. **Not using migrations.** `create_all` works once. After that, you need Alembic for schema changes.
2. **Forgetting to import models in Alembic's env.py.** Autogenerate can't detect models it doesn't know about.
3. **Not reviewing auto-generated migrations.** They can be wrong or incomplete.
4. **N+1 queries.** Loading related objects without eager loading. Use `selectinload` or `joinedload`.
5. **Committing sensitive database URLs.** Use environment variables.
6. **Not using transactions.** Every operation that writes should be inside a transaction.
7. **Mixing sync and async.** If you use `create_async_engine`, all operations must be async.

---

## Exercise: Full Database Migration

1. Start from the Task Manager API (Module 08)
2. Replace the in-memory store with SQLite + SQLAlchemy
3. Set up Alembic and create the initial migration
4. Add a `User` model with a one-to-many relationship to `Task`
5. Generate and apply the migration for the new relationship
6. Verify all CRUD operations work through `/docs`
7. Restart the server and confirm data persists

---

## Next Module

Proceed to `10_authentication_and_security.md` →
