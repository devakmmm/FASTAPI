# Module 06: Python Backend Basics

## Learning Objectives

By the end of this module, you will be able to:

- Set up a proper Python development environment
- Use virtual environments correctly
- Write type-annotated Python
- Understand async/await at a conceptual and practical level
- Use Python's HTTP libraries
- Structure a Python project for backend work
- Manage dependencies with pip and requirements files

---

## 6.1 Python Development Environment

### Verify Your Setup

```bash
python3 --version          # Should be 3.11+
pip3 --version             # Package installer
which python3              # Where it lives
```

### Virtual Environments — Non-Negotiable

A virtual environment is an isolated Python installation. Each project gets its own.

**Why?** Project A needs `fastapi==0.100.0`. Project B needs `fastapi==0.115.0`. Without virtual environments, they conflict.

```bash
# Create a virtual environment
python3 -m venv .venv

# Activate it
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Your prompt changes:
(.venv) $

# Verify isolation
which python              # Points to .venv/bin/python
which pip                 # Points to .venv/bin/pip

# Install packages (only in this environment)
pip install fastapi uvicorn

# Deactivate when done
deactivate
```

### requirements.txt

```bash
# Generate from current environment
pip freeze > requirements.txt

# Install from requirements
pip install -r requirements.txt
```

**Best practice:** Maintain two files:

```
# requirements.txt — direct dependencies (what YOU chose to install)
fastapi>=0.115.0,<1.0.0
uvicorn[standard]>=0.30.0,<1.0.0
sqlalchemy>=2.0.0,<3.0.0
pydantic>=2.0.0,<3.0.0

# requirements-dev.txt — development dependencies
-r requirements.txt
pytest>=8.0.0
httpx>=0.27.0
black>=24.0.0
ruff>=0.5.0
```

### Exercise 6.1: Environment Setup

```bash
mkdir backend-practice && cd backend-practice
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn httpx
pip freeze > requirements.txt
cat requirements.txt
```

---

## 6.2 Type Hints

Python is dynamically typed. Type hints add optional static type annotations. FastAPI uses them heavily for validation and documentation.

### Basic Type Hints

```python
# Variables
name: str = "Alice"
age: int = 30
price: float = 9.99
active: bool = True

# Functions
def greet(name: str) -> str:
    return f"Hello, {name}"

def add(a: int, b: int) -> int:
    return a + b

def process(data: str) -> None:
    print(data)
```

### Complex Types

```python
from typing import Optional

# Optional — can be the type OR None
def find_user(user_id: int) -> Optional[dict]:
    if user_id == 1:
        return {"id": 1, "name": "Alice"}
    return None

# Lists and dicts
def get_names() -> list[str]:
    return ["Alice", "Bob"]

def get_scores() -> dict[str, int]:
    return {"Alice": 95, "Bob": 87}

# Union — can be one of multiple types
from typing import Union

def parse_id(value: Union[str, int]) -> int:
    return int(value)

# Modern syntax (Python 3.10+)
def parse_id(value: str | int) -> int:
    return int(value)
```

### Why Type Hints Matter for FastAPI

FastAPI reads your type hints and uses them to:
1. **Validate** incoming request data
2. **Convert** data to the right type
3. **Generate** API documentation automatically
4. **Provide** editor autocompletion

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/items/{item_id}")
async def get_item(item_id: int, q: str | None = None):
    # FastAPI knows:
    # - item_id must be an integer (auto-converts from string)
    # - q is an optional query parameter
    return {"item_id": item_id, "q": q}
```

---

## 6.3 Pydantic — Data Validation

Pydantic is a data validation library. FastAPI is built on top of it.

### Basic Models

```python
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    age: int = Field(ge=0, le=150)
    role: str = "user"

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    created_at: datetime

# Valid
user = UserCreate(name="Alice", email="alice@example.com", age=30)
print(user.model_dump())
# {"name": "Alice", "email": "alice@example.com", "age": 30, "role": "user"}

# Invalid — raises ValidationError
try:
    bad_user = UserCreate(name="", email="not-an-email", age=-5)
except Exception as e:
    print(e)
```

### Key Pydantic Features

```python
from pydantic import BaseModel, field_validator

class Product(BaseModel):
    name: str
    price: float
    quantity: int

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Price must be positive")
        return round(v, 2)

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_non_negative(cls, v):
        if v < 0:
            raise ValueError("Quantity cannot be negative")
        return v

# Usage
product = Product(name="Widget", price=9.999, quantity=5)
print(product.price)     # 10.0 (rounded by validator)
print(product.model_dump())
print(product.model_dump_json())
```

### Exercise 6.2: Build Pydantic Models

Create Pydantic models for:

1. A `BlogPost` with title (required, 5-200 chars), content (required), tags (list of strings, optional), published (bool, default False)
2. A `Comment` with author (required), body (required, max 1000 chars), created_at (datetime, defaults to now)
3. A `BlogPostResponse` that includes the post data plus id and a list of comments

---

## 6.4 Async/Await — Understanding Concurrency

### The Problem

```python
import time

def fetch_user():
    time.sleep(1)      # Simulate network call
    return {"id": 1}

def fetch_orders():
    time.sleep(1)      # Simulate network call
    return [{"id": 101}]

def fetch_recommendations():
    time.sleep(1)      # Simulate network call
    return [{"id": 201}]

# Sequential: takes 3 seconds
user = fetch_user()
orders = fetch_orders()
recs = fetch_recommendations()
```

Three independent network calls that take 1 second each. Sequentially: 3 seconds. But they don't depend on each other. Why wait?

### The Solution: Async

```python
import asyncio

async def fetch_user():
    await asyncio.sleep(1)    # Non-blocking wait
    return {"id": 1}

async def fetch_orders():
    await asyncio.sleep(1)
    return [{"id": 101}]

async def fetch_recommendations():
    await asyncio.sleep(1)
    return [{"id": 201}]

async def main():
    # Concurrent: takes ~1 second (all three run simultaneously)
    user, orders, recs = await asyncio.gather(
        fetch_user(),
        fetch_orders(),
        fetch_recommendations()
    )
    print(user, orders, recs)

asyncio.run(main())
```

### How Async Works

```
Synchronous:
Task A: [████████████]
Task B:               [████████████]
Task C:                             [████████████]
Total:  ──────────────────────────────────────────── 3s

Asynchronous:
Task A: [████████████]
Task B: [████████████]
Task C: [████████████]
Total:  ──────────────── 1s
```

**Key concepts:**

- `async def` declares a coroutine (a function that can be paused)
- `await` pauses the coroutine and yields control to the event loop
- The event loop runs other coroutines while one is waiting
- This is NOT parallelism (not multiple threads). It is concurrency (one thread, switching between tasks while they wait for I/O)

### When to Use Async

```
USE async when:
  - Making HTTP requests to external services
  - Querying databases
  - Reading/writing files
  - Any I/O operation where you wait

DON'T need async when:
  - CPU-heavy computation (hashing, image processing)
  - Simple, fast operations
  - No I/O involved
```

### FastAPI and Async

```python
from fastapi import FastAPI

app = FastAPI()

# Async endpoint — good for I/O operations
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = await database.fetch_user(user_id)  # Non-blocking DB call
    return user

# Sync endpoint — FastAPI runs it in a thread pool
@app.get("/compute")
def compute():
    result = heavy_computation()  # Blocking is OK here
    return {"result": result}
```

FastAPI handles both. Use `async def` for I/O-bound endpoints. Use `def` for CPU-bound endpoints.

---

## 6.5 Making HTTP Requests

As a backend developer, your server often needs to call other APIs.

### Using `httpx` (Async HTTP Client)

```python
import httpx
import asyncio

async def main():
    async with httpx.AsyncClient() as client:
        # GET request
        response = await client.get("https://jsonplaceholder.typicode.com/users/1")
        print(response.status_code)    # 200
        print(response.json())         # Parsed JSON

        # POST request
        response = await client.post(
            "https://httpbin.org/post",
            json={"name": "Alice", "age": 30}
        )
        print(response.json())

        # With headers
        response = await client.get(
            "https://api.example.com/data",
            headers={"Authorization": "Bearer mytoken123"}
        )

asyncio.run(main())
```

### Using `requests` (Sync HTTP Client)

```python
import requests

# GET
response = requests.get("https://jsonplaceholder.typicode.com/users/1")
print(response.status_code)
print(response.json())

# POST
response = requests.post(
    "https://httpbin.org/post",
    json={"name": "Alice", "age": 30}
)

# Error handling
response = requests.get("https://httpbin.org/status/404")
response.raise_for_status()    # Raises HTTPError for 4xx/5xx
```

### Exercise 6.3: API Consumer

Build a script that:

1. Fetches a list of users from `https://jsonplaceholder.typicode.com/users`
2. For each user, fetches their posts from `https://jsonplaceholder.typicode.com/users/{id}/posts`
3. Prints a summary: "User {name} has {n} posts"
4. Do it both synchronously and asynchronously. Time both. Compare.

---

## 6.6 Project Structure

A well-structured Python backend project:

```
my-api/
├── .venv/                  # Virtual environment (gitignored)
├── .env                    # Environment variables (gitignored)
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app creation, startup
│   ├── config.py          # Settings and configuration
│   ├── models/            # Pydantic models (schemas)
│   │   ├── __init__.py
│   │   └── user.py
│   ├── routes/            # API endpoints
│   │   ├── __init__.py
│   │   └── users.py
│   ├── services/          # Business logic
│   │   ├── __init__.py
│   │   └── user_service.py
│   ├── database/          # Database connection, ORM models
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   └── models.py
│   └── utils/             # Shared utilities
│       ├── __init__.py
│       └── security.py
└── tests/
    ├── __init__.py
    ├── conftest.py        # Shared test fixtures
    ├── test_users.py
    └── test_auth.py
```

### Key Principles

1. **Separate concerns.** Routes handle HTTP. Services handle logic. Models handle data shapes.
2. **No business logic in routes.** Routes call services. Services call databases.
3. **Configuration from environment.** Never hardcode secrets, URLs, or settings.

---

## 6.7 Configuration Management

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "My API"
    debug: bool = False
    database_url: str
    secret_key: str
    allowed_origins: list[str] = ["http://localhost:3000"]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

settings = Settings()
```

```bash
# .env
DATABASE_URL=postgresql://user:pass@localhost:5432/mydb
SECRET_KEY=your-secret-key-here
DEBUG=true
```

```python
# Usage anywhere in the app
from app.config import settings

print(settings.database_url)
print(settings.debug)
```

---

## 6.8 Python Decorators (Essential for FastAPI)

Decorators wrap functions with additional behavior. FastAPI uses them for routing.

```python
# A decorator is a function that takes a function and returns a modified function

def log_calls(func):
    def wrapper(*args, **kwargs):
        print(f"Calling {func.__name__}")
        result = func(*args, **kwargs)
        print(f"{func.__name__} returned {result}")
        return result
    return wrapper

@log_calls
def add(a, b):
    return a + b

add(2, 3)
# Calling add
# add returned 5
```

In FastAPI:

```python
@app.get("/users")          # @app.get is a decorator
async def list_users():     # This function is registered as the handler for GET /users
    return [...]
```

The `@app.get("/users")` decorator registers `list_users` as the handler function for `GET /users`. You don't call `list_users()` yourself — FastAPI calls it when a matching request arrives.

---

## Checkpoint Quiz

1. Why are virtual environments necessary?
2. What does `pip freeze` do?
3. What is the difference between `async def` and `def` in FastAPI?
4. When should you use async? When is it unnecessary?
5. What does Pydantic do?
6. What is a type hint? Why does FastAPI need them?
7. What belongs in `routes/` vs `services/` vs `models/`?
8. Why should configuration come from environment variables?
9. What does `await` do?
10. How do you activate a virtual environment?

---

## Common Mistakes

1. **Not using virtual environments.** Installing packages globally pollutes your system Python and causes version conflicts.
2. **Forgetting to activate the venv.** You install packages globally instead of in the venv. Check your prompt for `(.venv)`.
3. **Mixing async and sync incorrectly.** Calling a sync blocking function inside an `async def` blocks the event loop. Use `def` for sync handlers in FastAPI, or run blocking code in a thread pool.
4. **Not using type hints.** FastAPI cannot validate or document without them. They are not optional in FastAPI.
5. **Hardcoding configuration.** Database URLs, secrets, and API keys belong in environment variables, not in source code.
6. **One giant file.** Split your app into modules from the start. It is much harder to refactor later.

---

## Mini Project: Async API Aggregator

Build a Python script that:

1. Takes a list of API endpoints as input
2. Fetches all of them concurrently using `asyncio.gather` and `httpx`
3. Reports: URL, status code, response time, body size
4. Prints a summary with total time (demonstrating async advantage)

```python
# api_aggregator.py
import asyncio
import httpx
import time

URLS = [
    "https://jsonplaceholder.typicode.com/posts/1",
    "https://jsonplaceholder.typicode.com/users/1",
    "https://jsonplaceholder.typicode.com/comments/1",
    "https://jsonplaceholder.typicode.com/todos/1",
    "https://jsonplaceholder.typicode.com/albums/1",
]

async def fetch(client: httpx.AsyncClient, url: str) -> dict:
    start = time.time()
    response = await client.get(url)
    elapsed = time.time() - start
    return {
        "url": url,
        "status": response.status_code,
        "time_ms": round(elapsed * 1000),
        "size_bytes": len(response.content),
    }

async def main():
    start = time.time()
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[fetch(client, url) for url in URLS])

    total = time.time() - start

    for r in results:
        print(f"  {r['status']} | {r['time_ms']:>4}ms | {r['size_bytes']:>6}B | {r['url']}")

    print(f"\nTotal time: {round(total * 1000)}ms for {len(URLS)} requests")
    print(f"Sequential estimate: ~{sum(r['time_ms'] for r in results)}ms")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Next Module

Proceed to `07_fastapi_core_concepts.md` →
