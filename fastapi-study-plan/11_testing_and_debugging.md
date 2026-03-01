# Module 11: Testing and Debugging

## Learning Objectives

By the end of this module, you will be able to:

- Explain why testing matters and what to test
- Write unit tests and integration tests with pytest
- Use FastAPI's TestClient to test API endpoints
- Set up test fixtures and test databases
- Debug FastAPI applications systematically
- Use logging effectively
- Measure test coverage
- Follow testing best practices

---

## 11.1 Why Test?

Testing is not extra work. It is the work. Code without tests is a liability.

### What Testing Gives You

1. **Confidence to change code.** Refactoring without tests is gambling.
2. **Documentation.** Tests show how code is supposed to behave.
3. **Bug prevention.** Catch regressions before users do.
4. **Design feedback.** Hard-to-test code is usually poorly designed.

### Types of Tests

```
┌─────────────────────────────────────┐
│          End-to-End Tests           │  Few (slow, brittle)
│    Full system, browser, network    │
├─────────────────────────────────────┤
│        Integration Tests            │  Some (moderate speed)
│    Multiple components together     │
│    API endpoints, database calls    │
├─────────────────────────────────────┤
│          Unit Tests                 │  Many (fast, focused)
│    Single function or class         │
│    Isolated from external systems   │
└─────────────────────────────────────┘
         The Testing Pyramid
```

For backend APIs, most of your tests will be **integration tests** (testing endpoints with a real/test database).

---

## 11.2 Setup

```bash
pip install pytest pytest-asyncio httpx

# Project structure
tests/
├── __init__.py
├── conftest.py          # Shared fixtures
├── test_tasks.py        # Task endpoint tests
├── test_auth.py         # Auth endpoint tests
└── test_services.py     # Service layer tests
```

### Configuration

```ini
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## 11.3 Test Client and Fixtures

### conftest.py — The Foundation

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.database import Base, get_db

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_database():
    """Create tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    """Async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_client(client: AsyncClient):
    """Authenticated test client."""
    # Register a user
    await client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123",
    })

    # Get token
    response = await client.post("/api/v1/auth/token", data={
        "username": "testuser",
        "password": "testpassword123",
    })
    token = response.json()["access_token"]

    client.headers["Authorization"] = f"Bearer {token}"
    yield client
```

---

## 11.4 Writing Tests

### Testing CRUD Endpoints

```python
# tests/test_tasks.py
import pytest
from httpx import AsyncClient

class TestCreateTask:
    async def test_create_task_success(self, auth_client: AsyncClient):
        response = await auth_client.post("/api/v1/tasks/", json={
            "title": "Test task",
            "description": "A test task",
            "priority": "high",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test task"
        assert data["priority"] == "high"
        assert data["status"] == "todo"
        assert "id" in data
        assert "created_at" in data

    async def test_create_task_missing_title(self, auth_client: AsyncClient):
        response = await auth_client.post("/api/v1/tasks/", json={
            "description": "No title provided",
        })
        assert response.status_code == 422

    async def test_create_task_title_too_long(self, auth_client: AsyncClient):
        response = await auth_client.post("/api/v1/tasks/", json={
            "title": "x" * 201,
        })
        assert response.status_code == 422

    async def test_create_task_unauthenticated(self, client: AsyncClient):
        response = await client.post("/api/v1/tasks/", json={
            "title": "Should fail",
        })
        assert response.status_code == 401


class TestGetTask:
    async def test_get_existing_task(self, auth_client: AsyncClient):
        # Create first
        create_response = await auth_client.post("/api/v1/tasks/", json={
            "title": "Get me",
        })
        task_id = create_response.json()["id"]

        # Get
        response = await auth_client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["title"] == "Get me"

    async def test_get_nonexistent_task(self, auth_client: AsyncClient):
        response = await auth_client.get("/api/v1/tasks/99999")
        assert response.status_code == 404


class TestListTasks:
    async def test_list_empty(self, auth_client: AsyncClient):
        response = await auth_client.get("/api/v1/tasks/")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["total"] == 0

    async def test_list_with_tasks(self, auth_client: AsyncClient):
        # Create 3 tasks
        for i in range(3):
            await auth_client.post("/api/v1/tasks/", json={
                "title": f"Task {i}",
            })

        response = await auth_client.get("/api/v1/tasks/")
        data = response.json()
        assert data["total"] == 3
        assert len(data["data"]) == 3

    async def test_list_with_pagination(self, auth_client: AsyncClient):
        for i in range(5):
            await auth_client.post("/api/v1/tasks/", json={
                "title": f"Task {i}",
            })

        response = await auth_client.get("/api/v1/tasks/?page=1&per_page=2")
        data = response.json()
        assert len(data["data"]) == 2
        assert data["total"] == 5
        assert data["total_pages"] == 3

    async def test_filter_by_status(self, auth_client: AsyncClient):
        # Create a task and mark it done
        create_resp = await auth_client.post("/api/v1/tasks/", json={
            "title": "Done task",
        })
        task_id = create_resp.json()["id"]
        await auth_client.patch(f"/api/v1/tasks/{task_id}", json={
            "status": "done",
        })

        # Create a todo task
        await auth_client.post("/api/v1/tasks/", json={
            "title": "Todo task",
        })

        # Filter
        response = await auth_client.get("/api/v1/tasks/?status=done")
        data = response.json()
        assert data["total"] == 1
        assert data["data"][0]["status"] == "done"


class TestUpdateTask:
    async def test_update_task(self, auth_client: AsyncClient):
        create_resp = await auth_client.post("/api/v1/tasks/", json={
            "title": "Original",
        })
        task_id = create_resp.json()["id"]

        response = await auth_client.patch(f"/api/v1/tasks/{task_id}", json={
            "title": "Updated",
            "status": "in_progress",
        })
        assert response.status_code == 200
        assert response.json()["title"] == "Updated"
        assert response.json()["status"] == "in_progress"

    async def test_partial_update(self, auth_client: AsyncClient):
        create_resp = await auth_client.post("/api/v1/tasks/", json={
            "title": "Keep this",
            "priority": "high",
        })
        task_id = create_resp.json()["id"]

        # Only update status, title and priority should remain
        response = await auth_client.patch(f"/api/v1/tasks/{task_id}", json={
            "status": "done",
        })
        data = response.json()
        assert data["title"] == "Keep this"
        assert data["priority"] == "high"
        assert data["status"] == "done"


class TestDeleteTask:
    async def test_delete_task(self, auth_client: AsyncClient):
        create_resp = await auth_client.post("/api/v1/tasks/", json={
            "title": "Delete me",
        })
        task_id = create_resp.json()["id"]

        response = await auth_client.delete(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = await auth_client.get(f"/api/v1/tasks/{task_id}")
        assert get_resp.status_code == 404

    async def test_delete_nonexistent(self, auth_client: AsyncClient):
        response = await auth_client.delete("/api/v1/tasks/99999")
        assert response.status_code == 404
```

### Testing Authentication

```python
# tests/test_auth.py
import pytest
from httpx import AsyncClient

class TestRegistration:
    async def test_register_success(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "securepass123",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newuser"
        assert "password" not in data
        assert "hashed_password" not in data

    async def test_register_duplicate_username(self, client: AsyncClient):
        user_data = {
            "username": "duplicate",
            "email": "dup@example.com",
            "password": "securepass123",
        }
        await client.post("/api/v1/auth/register", json=user_data)
        response = await client.post("/api/v1/auth/register", json=user_data)
        assert response.status_code == 409

    async def test_register_weak_password(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "username": "user",
            "email": "user@example.com",
            "password": "short",
        })
        assert response.status_code == 422


class TestLogin:
    async def test_login_success(self, client: AsyncClient):
        # Register first
        await client.post("/api/v1/auth/register", json={
            "username": "loginuser",
            "email": "login@example.com",
            "password": "securepass123",
        })

        response = await client.post("/api/v1/auth/token", data={
            "username": "loginuser",
            "password": "securepass123",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "loginuser2",
            "email": "login2@example.com",
            "password": "securepass123",
        })

        response = await client.post("/api/v1/auth/token", data={
            "username": "loginuser2",
            "password": "wrongpassword",
        })
        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/token", data={
            "username": "nobody",
            "password": "whatever",
        })
        assert response.status_code == 401
```

---

## 11.5 Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific file
pytest tests/test_tasks.py

# Run a specific test class
pytest tests/test_tasks.py::TestCreateTask

# Run a specific test
pytest tests/test_tasks.py::TestCreateTask::test_create_task_success

# Run with print output visible
pytest -s

# Run and stop on first failure
pytest -x

# Run tests matching a pattern
pytest -k "test_create"

# Run with coverage
pip install pytest-cov
pytest --cov=app --cov-report=term-missing
```

### Reading Coverage Output

```
Name                          Stmts   Miss  Cover   Missing
------------------------------------------------------------
app/__init__.py                   0      0   100%
app/main.py                      18      0   100%
app/models.py                    45      0   100%
app/routes/tasks.py              32      2    94%   45-46
app/services/task_service.py     58      5    91%   72-78
------------------------------------------------------------
TOTAL                           153      7    95%
```

`Missing` shows line numbers without test coverage. Aim for 80%+ coverage on business logic.

---

## 11.6 Testing Best Practices

### 1. Test Behavior, Not Implementation

```python
# BAD: Tests implementation details
async def test_task_stored_in_dict(self, auth_client):
    from app.database import tasks_db
    await auth_client.post("/api/v1/tasks/", json={"title": "Test"})
    assert len(tasks_db) == 1

# GOOD: Tests behavior
async def test_created_task_is_retrievable(self, auth_client):
    create_resp = await auth_client.post("/api/v1/tasks/", json={"title": "Test"})
    task_id = create_resp.json()["id"]

    get_resp = await auth_client.get(f"/api/v1/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Test"
```

### 2. Each Test Should Be Independent

Tests should not depend on each other. Each test creates its own data.

### 3. Test Edge Cases

- Empty inputs
- Maximum-length inputs
- Special characters
- Zero, negative numbers
- Nonexistent IDs
- Duplicate creation
- Concurrent modifications

### 4. Name Tests Clearly

The test name should describe what is being tested and what the expected outcome is:

```python
test_create_task_success
test_create_task_missing_title_returns_422
test_get_nonexistent_task_returns_404
test_update_preserves_unchanged_fields
test_delete_task_makes_it_unretrievable
```

---

## 11.7 Debugging

### Structured Logging

```python
# app/utils/logging.py
import logging
import sys

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

logger = logging.getLogger("taskmanager")
```

```python
# Usage in services
from app.utils.logging import logger

async def create_task(db, data, owner_id):
    logger.info(f"Creating task '{data.title}' for user {owner_id}")
    try:
        task = Task(title=data.title, owner_id=owner_id)
        db.add(task)
        await db.flush()
        logger.info(f"Task {task.id} created successfully")
        return task
    except Exception as e:
        logger.error(f"Failed to create task: {e}", exc_info=True)
        raise
```

### Request Logging Middleware

```python
import time
import uuid
from fastapi import Request
from app.utils.logging import logger

@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start = time.time()

    logger.info(f"[{request_id}] {request.method} {request.url.path}")

    response = await call_next(request)

    duration = round((time.time() - start) * 1000, 2)
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} "
        f"→ {response.status_code} ({duration}ms)"
    )

    response.headers["X-Request-ID"] = request_id
    return response
```

### Debugging Strategy

When something goes wrong:

```
1. READ THE ERROR MESSAGE. Completely. Every word.
2. Check the status code.
3. Check the request — did you send what you think you sent?
4. Check the logs — what did the server see?
5. Reproduce with curl — isolate the problem.
6. Add logging around the failing code.
7. Check the database — is the data what you expect?
8. Run the specific test in isolation.
```

### Common Debug Commands

```bash
# Check if server is running
curl http://localhost:8000/health

# See raw request/response
curl -v http://localhost:8000/api/v1/tasks

# Check database directly
sqlite3 taskmanager.db "SELECT * FROM tasks;"
sqlite3 taskmanager.db ".schema tasks"

# Watch logs
uvicorn app.main:app --reload --log-level debug

# Run one test with full output
pytest tests/test_tasks.py::TestCreateTask::test_create_task_success -v -s
```

---

## Checkpoint Quiz

1. What is the testing pyramid? Why is it shaped that way?
2. What is the difference between a unit test and an integration test?
3. Why does each test need its own database state?
4. What does `pytest --cov` show you?
5. Why test error cases, not just happy paths?
6. What is a test fixture? What does `conftest.py` do?
7. How do you override a FastAPI dependency in tests?
8. What should you do first when debugging a failing API call?
9. Why use structured logging instead of `print()`?
10. What does the `-x` flag do in pytest?

---

## Common Mistakes

1. **Not testing error cases.** If you only test the happy path, bugs hide in error handling.
2. **Tests depending on each other.** Test A creates data that Test B uses. If A fails, B fails for the wrong reason.
3. **Testing against the production database.** Always use a separate test database.
4. **Not running tests before committing.** Make it a habit: test, then commit.
5. **Testing framework internals.** Don't test that FastAPI returns 422 for invalid input — that is FastAPI's job. Test YOUR logic.
6. **No logging.** When production breaks at 3am, logs are all you have.
7. **Using `print()` for debugging.** Use `logging`. It has levels, formatting, and can be configured.

---

## Exercise: Full Test Suite

Write a complete test suite for the Task Manager API:

1. CRUD tests for every endpoint (happy path + error cases)
2. Authentication tests (registration, login, token validation)
3. Authorization tests (accessing other users' tasks)
4. Pagination tests
5. Filter and search tests
6. Edge case tests (empty strings, boundary values)
7. Achieve 85%+ code coverage

Run: `pytest --cov=app --cov-report=html` and open `htmlcov/index.html` to visualize coverage.

---

## Next Module

Proceed to `12_deployment_and_production.md` →
