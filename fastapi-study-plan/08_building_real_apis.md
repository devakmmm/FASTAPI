# Module 08: Building Real APIs

## Learning Objectives

By the end of this module, you will be able to:

- Build a complete CRUD API from scratch, progressively
- Structure a multi-file FastAPI application
- Implement proper input validation and error handling
- Use API routers for organization
- Consume and test APIs using curl, HTTPie, Postman, and Python
- Read and understand OpenAPI documentation
- Apply everything from previous modules in a real project

---

## 8.1 Project Setup

We are building a **Task Manager API**. Start from scratch.

```bash
mkdir task-manager && cd task-manager
python3 -m venv .venv
source .venv/bin/activate
pip install "fastapi[standard]" httpx
```

### Project Structure

```
task-manager/
├── .venv/
├── .gitignore
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── routes/
│   │   ├── __init__.py
│   │   └── tasks.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── task_service.py
│   └── database.py
└── tests/
    ├── __init__.py
    └── test_tasks.py
```

```bash
mkdir -p app/routes app/services tests
touch app/__init__.py app/routes/__init__.py app/services/__init__.py tests/__init__.py
```

---

## 8.2 Step 1 — Models

Define the data shapes first. Always.

```python
# app/models.py
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class TaskStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    priority: Priority = Priority.medium
    due_date: datetime | None = None
    tags: list[str] = []

class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    priority: Priority | None = None
    status: TaskStatus | None = None
    due_date: datetime | None = None
    tags: list[str] | None = None

class TaskResponse(BaseModel):
    id: int
    title: str
    description: str | None
    priority: Priority
    status: TaskStatus
    due_date: datetime | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime

class TaskListResponse(BaseModel):
    data: list[TaskResponse]
    total: int
    page: int
    per_page: int
    total_pages: int
```

---

## 8.3 Step 2 — In-Memory Database

Before adding a real database, use an in-memory store. This lets you focus on API design.

```python
# app/database.py
from datetime import datetime
from app.models import TaskStatus, Priority

tasks_db: dict[int, dict] = {}
next_id: int = 1

def get_next_id() -> int:
    global next_id
    current = next_id
    next_id += 1
    return current

def seed_data():
    """Add sample data for development."""
    global next_id
    samples = [
        {
            "title": "Set up project structure",
            "description": "Initialize FastAPI project with proper layout",
            "priority": Priority.high,
            "status": TaskStatus.done,
            "tags": ["setup", "infrastructure"],
        },
        {
            "title": "Implement CRUD endpoints",
            "description": "Build all task management endpoints",
            "priority": Priority.high,
            "status": TaskStatus.in_progress,
            "tags": ["api", "backend"],
        },
        {
            "title": "Write tests",
            "description": "Add comprehensive test coverage",
            "priority": Priority.medium,
            "status": TaskStatus.todo,
            "tags": ["testing"],
        },
    ]
    for sample in samples:
        task_id = get_next_id()
        now = datetime.now()
        tasks_db[task_id] = {
            "id": task_id,
            **sample,
            "due_date": None,
            "created_at": now,
            "updated_at": now,
        }
```

---

## 8.4 Step 3 — Service Layer

Business logic lives here. Routes should be thin wrappers.

```python
# app/services/task_service.py
import math
from datetime import datetime
from fastapi import HTTPException
from app.models import TaskCreate, TaskUpdate, TaskResponse, TaskStatus
from app.database import tasks_db, get_next_id

def create_task(data: TaskCreate) -> TaskResponse:
    task_id = get_next_id()
    now = datetime.now()
    task = {
        "id": task_id,
        "title": data.title,
        "description": data.description,
        "priority": data.priority,
        "status": TaskStatus.todo,
        "due_date": data.due_date,
        "tags": data.tags,
        "created_at": now,
        "updated_at": now,
    }
    tasks_db[task_id] = task
    return TaskResponse(**task)

def get_task(task_id: int) -> TaskResponse:
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskResponse(**task)

def list_tasks(
    page: int = 1,
    per_page: int = 20,
    status: TaskStatus | None = None,
    priority: str | None = None,
    search: str | None = None,
) -> dict:
    filtered = list(tasks_db.values())

    if status:
        filtered = [t for t in filtered if t["status"] == status]
    if priority:
        filtered = [t for t in filtered if t["priority"] == priority]
    if search:
        search_lower = search.lower()
        filtered = [
            t for t in filtered
            if search_lower in t["title"].lower()
            or (t["description"] and search_lower in t["description"].lower())
        ]

    total = len(filtered)
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    start = (page - 1) * per_page
    end = start + per_page
    paginated = filtered[start:end]

    return {
        "data": [TaskResponse(**t) for t in paginated],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }

def update_task(task_id: int, data: TaskUpdate) -> TaskResponse:
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        task[key] = value
    task["updated_at"] = datetime.now()

    return TaskResponse(**task)

def delete_task(task_id: int) -> None:
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    del tasks_db[task_id]
```

---

## 8.5 Step 4 — Routes

```python
# app/routes/tasks.py
from fastapi import APIRouter, Query
from app.models import (
    TaskCreate, TaskUpdate, TaskResponse,
    TaskListResponse, TaskStatus, Priority,
)
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(task: TaskCreate):
    """Create a new task."""
    return task_service.create_task(task)

@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: TaskStatus | None = None,
    priority: Priority | None = None,
    search: str | None = Query(default=None, min_length=1),
):
    """List tasks with filtering and pagination."""
    return task_service.list_tasks(
        page=page,
        per_page=per_page,
        status=status,
        priority=priority,
        search=search,
    )

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    """Get a specific task by ID."""
    return task_service.get_task(task_id)

@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, task: TaskUpdate):
    """Partially update a task."""
    return task_service.update_task(task_id, task)

@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: int):
    """Delete a task."""
    task_service.delete_task(task_id)
```

---

## 8.6 Step 5 — Main Application

```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import tasks
from app.database import seed_data

app = FastAPI(
    title="Task Manager API",
    description="A production-oriented task management API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router, prefix="/api/v1")

@app.on_event("startup")
async def startup():
    seed_data()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### Run and Verify

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs — your entire API is documented.

---

## 8.7 Consuming and Testing APIs

### Using curl

```bash
# Health check
curl http://localhost:8000/health

# List tasks
curl http://localhost:8000/api/v1/tasks

# Create a task
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Learn FastAPI",
    "description": "Complete the study plan",
    "priority": "high",
    "tags": ["learning", "python"]
  }'

# Get a specific task
curl http://localhost:8000/api/v1/tasks/1

# Update a task
curl -X PATCH http://localhost:8000/api/v1/tasks/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "done"}'

# Delete a task
curl -X DELETE http://localhost:8000/api/v1/tasks/1

# Filter by status
curl "http://localhost:8000/api/v1/tasks?status=todo"

# Search
curl "http://localhost:8000/api/v1/tasks?search=test"

# Pagination
curl "http://localhost:8000/api/v1/tasks?page=1&per_page=5"
```

### Using HTTPie

HTTPie is curl with better syntax:

```bash
pip install httpie

# GET
http GET localhost:8000/api/v1/tasks

# POST (JSON by default)
http POST localhost:8000/api/v1/tasks \
  title="Deploy to production" \
  priority="critical" \
  tags:='["devops", "deployment"]'

# PATCH
http PATCH localhost:8000/api/v1/tasks/1 \
  status="done"

# DELETE
http DELETE localhost:8000/api/v1/tasks/1

# With headers
http GET localhost:8000/api/v1/tasks \
  Authorization:"Bearer mytoken"
```

### Using Postman

1. Open Postman
2. Import from URL: `http://localhost:8000/openapi.json`
3. Postman auto-generates a collection from your OpenAPI spec
4. Each endpoint is pre-configured — just click "Send"

### Using Python (httpx)

```python
import httpx

BASE = "http://localhost:8000/api/v1"

with httpx.Client() as client:
    # Create
    response = client.post(f"{BASE}/tasks", json={
        "title": "API test task",
        "priority": "high",
    })
    print(response.status_code)    # 201
    task = response.json()
    print(task)

    # Read
    response = client.get(f"{BASE}/tasks/{task['id']}")
    print(response.json())

    # Update
    response = client.patch(f"{BASE}/tasks/{task['id']}", json={
        "status": "done"
    })
    print(response.json())

    # Delete
    response = client.delete(f"{BASE}/tasks/{task['id']}")
    print(response.status_code)    # 204
```

### Using fetch in JavaScript

```javascript
// List tasks
const response = await fetch('http://localhost:8000/api/v1/tasks');
const data = await response.json();
console.log(data);

// Create task
const createResponse = await fetch('http://localhost:8000/api/v1/tasks', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    title: 'From JavaScript',
    priority: 'medium',
  }),
});
const newTask = await createResponse.json();
console.log(newTask);
```

---

## 8.8 Understanding OpenAPI

FastAPI auto-generates an OpenAPI specification. This is the industry standard for API documentation.

### Where to Find It

```
http://localhost:8000/openapi.json   → Raw spec (JSON)
http://localhost:8000/docs           → Swagger UI (interactive)
http://localhost:8000/redoc          → ReDoc (readable)
```

### Reading the Swagger UI

The Swagger UI at `/docs` shows:

1. **All endpoints** grouped by tags
2. **Request parameters** (path, query, body) with types and validation rules
3. **Response schemas** with example data
4. **"Try it out" button** to make live requests from the browser
5. **Response codes** and their meanings

**Use this as your primary development tool.** It is faster than writing curl commands.

### Adding Documentation to Your API

```python
@router.post(
    "/",
    response_model=TaskResponse,
    status_code=201,
    summary="Create a new task",
    description="Creates a task with the given data. Returns the created task.",
    responses={
        201: {"description": "Task created successfully"},
        422: {"description": "Validation error in request body"},
    },
)
async def create_task(task: TaskCreate):
    return task_service.create_task(task)
```

---

## 8.9 Progressive Enhancement Exercises

### Exercise 8.1: Add Statistics Endpoint

Add `GET /api/v1/tasks/stats` that returns:

```json
{
  "total": 15,
  "by_status": {
    "todo": 5,
    "in_progress": 3,
    "done": 6,
    "cancelled": 1
  },
  "by_priority": {
    "low": 2,
    "medium": 5,
    "high": 6,
    "critical": 2
  },
  "overdue": 3
}
```

### Exercise 8.2: Add Bulk Operations

Add `POST /api/v1/tasks/bulk` that creates multiple tasks at once.
Add `PATCH /api/v1/tasks/bulk-status` that updates the status of multiple tasks by ID.

### Exercise 8.3: Add Sorting

Extend the list endpoint to support sorting:
```
GET /api/v1/tasks?sort_by=created_at&order=desc
GET /api/v1/tasks?sort_by=priority&order=asc
```

### Exercise 8.4: Add Tags Endpoint

Add `GET /api/v1/tags` that returns all unique tags across all tasks with counts:

```json
{
  "tags": [
    {"name": "python", "count": 5},
    {"name": "testing", "count": 3},
    {"name": "devops", "count": 2}
  ]
}
```

---

## Checkpoint Quiz

1. Why should business logic live in the service layer, not in routes?
2. What does `exclude_unset=True` do in `model_dump()`? Why is it important for PATCH?
3. How does FastAPI know which parameters are path vs query vs body?
4. What HTTP status code should a successful POST return?
5. What is the purpose of the OpenAPI specification?
6. What is the difference between `http` (HTTPie) and `curl`?
7. Why does the list endpoint need pagination?
8. What does `tags=["tasks"]` do in the APIRouter?
9. How would a JavaScript frontend consume this API?
10. Why seed data on startup during development?

---

## Common Mistakes

1. **Putting logic in routes.** Routes should parse input, call a service, return output. Nothing else.
2. **Not using `model_dump(exclude_unset=True)` for PATCH.** Without it, you can't distinguish between "field not sent" and "field sent as None."
3. **Forgetting status codes.** POST should return 201. DELETE should return 204. GET should return 200.
4. **Not testing error cases.** Test with invalid data, missing fields, nonexistent IDs.
5. **Hardcoding the API prefix.** Use constants or config, not string literals everywhere.
6. **No health check endpoint.** Every API needs one. Load balancers and monitoring tools use it.
7. **Returning the raw database object.** Always use a response model to control what the client sees.

---

## Next Module

Proceed to `09_database_integration.md` →
