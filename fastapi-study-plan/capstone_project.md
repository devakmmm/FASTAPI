# Capstone Project: Production-Ready Task Management API

## Overview

Build a complete, production-ready FastAPI backend from scratch. This project integrates every concept from the curriculum into a single, deployable application.

**What you will build:** A task management API with user accounts, authentication, full CRUD, database persistence, Docker containerization, and deployment.

**Time estimate:** 1–2 weeks (after completing all prior modules).

---

## Requirements

### Functional Requirements

1. **User Management**
   - Register with username, email, password
   - Login with JWT token authentication
   - Get current user profile
   - Update profile
   - Change password

2. **Task Management (CRUD)**
   - Create tasks with title, description, priority, due date, tags
   - List tasks with filtering (status, priority, search), sorting, and pagination
   - Get single task by ID
   - Update task (partial updates with PATCH)
   - Delete task
   - Users can only access their own tasks

3. **Task Organization**
   - Mark tasks as todo / in_progress / done / cancelled
   - Set priority: low / medium / high / critical
   - Tag tasks with labels
   - Filter by status, priority, tag, date range
   - Search tasks by title and description

4. **Statistics**
   - Task count by status
   - Task count by priority
   - Overdue task count
   - Tasks completed this week

### Non-Functional Requirements

1. Input validation on all endpoints
2. Proper HTTP status codes
3. Structured error responses
4. Request logging with timing
5. Health check endpoint
6. API documentation (auto-generated)
7. Test coverage > 80%
8. Docker containerization
9. Environment-based configuration
10. Git version control with meaningful commits

---

## Project Structure

```
task-manager-capstone/
├── .github/
│   └── workflows/
│       └── ci.yml
├── alembic/
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── db_models.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── task.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── users.py
│   │   └── tasks.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── user_service.py
│   │   └── task_service.py
│   └── utils/
│       ├── __init__.py
│       ├── security.py
│       └── logging.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_users.py
│   ├── test_tasks.py
│   └── test_stats.py
├── .dockerignore
├── .env.example
├── .gitignore
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── gunicorn.conf.py
├── nginx.conf
├── pyproject.toml
├── README.md
├── requirements.txt
└── requirements-dev.txt
```

---

## Build Checklist

Work through these phases in order. Do not skip ahead.

### Phase 1: Foundation

```
[ ] Create Git repository
[ ] Initialize project structure (all directories and __init__.py files)
[ ] Create virtual environment
[ ] Install dependencies and generate requirements.txt
[ ] Create .gitignore (Python + Docker + IDE + .env)
[ ] Create .env.example with all required variables
[ ] Create app/config.py with Pydantic Settings
[ ] Create app/database.py with async SQLAlchemy engine
[ ] Create app/main.py with FastAPI app, CORS, health check
[ ] Verify: uvicorn starts and /health returns 200
[ ] Git commit: "Initialize project structure"
```

### Phase 2: Database Models

```
[ ] Define User model in app/db_models.py
    - id, username, email, hashed_password, is_active, role, created_at
[ ] Define Task model in app/db_models.py
    - id, title, description, priority, status, due_date, tags, owner_id
    - Foreign key to User
[ ] Create Pydantic models in app/models/user.py
    - UserCreate, UserUpdate, UserResponse
[ ] Create Pydantic models in app/models/task.py
    - TaskCreate, TaskUpdate, TaskResponse, TaskListResponse
[ ] Set up Alembic
[ ] Generate initial migration
[ ] Apply migration
[ ] Verify: tables exist in database
[ ] Git commit: "Add database models and migrations"
```

### Phase 3: Authentication

```
[ ] Implement password hashing in app/utils/security.py
[ ] Implement JWT creation and validation
[ ] Create auth service (register, login, get_current_user)
[ ] Create auth routes (POST /register, POST /token, GET /me)
[ ] Test registration with curl
[ ] Test login with curl
[ ] Test /me with token
[ ] Test /me without token (should 401)
[ ] Git commit: "Add user authentication"
```

### Phase 4: Task CRUD

```
[ ] Implement task service (create, get, list, update, delete)
[ ] Implement task routes with authentication dependency
    - POST   /api/v1/tasks
    - GET    /api/v1/tasks
    - GET    /api/v1/tasks/{id}
    - PATCH  /api/v1/tasks/{id}
    - DELETE /api/v1/tasks/{id}
[ ] Add filtering: status, priority, search query
[ ] Add sorting: created_at, priority, due_date
[ ] Add pagination: page, per_page
[ ] Ensure users can only access their own tasks
[ ] Test all endpoints with curl and /docs
[ ] Git commit: "Add task CRUD with filtering and pagination"
```

### Phase 5: Statistics

```
[ ] Implement stats service
[ ] Add GET /api/v1/tasks/stats endpoint
[ ] Return counts by status, priority, overdue count
[ ] Test with curl
[ ] Git commit: "Add task statistics endpoint"
```

### Phase 6: Middleware and Polish

```
[ ] Add request logging middleware (method, path, status, timing)
[ ] Add request ID middleware
[ ] Add proper error handling (custom exception handlers)
[ ] Add rate limiting on /token endpoint (optional)
[ ] Review all response models — ensure no sensitive data leaks
[ ] Review all status codes
[ ] Git commit: "Add middleware, logging, and error handling"
```

### Phase 7: Testing

```
[ ] Set up test infrastructure (conftest.py, test database)
[ ] Write auth tests
    - Registration (success, duplicate, validation errors)
    - Login (success, wrong password, nonexistent user)
    - Token validation (valid, expired, malformed)
[ ] Write task CRUD tests
    - Create (success, validation errors, unauthenticated)
    - Read (existing, nonexistent, other user's task)
    - List (empty, with data, pagination, filters)
    - Update (success, partial, nonexistent, other user's)
    - Delete (success, nonexistent, other user's)
[ ] Write stats tests
[ ] Write edge case tests
[ ] Run coverage: pytest --cov=app --cov-report=term-missing
[ ] Achieve > 80% coverage
[ ] Git commit: "Add comprehensive test suite"
```

### Phase 8: Docker

```
[ ] Write Dockerfile (multi-stage if desired)
[ ] Write .dockerignore
[ ] Write docker-compose.yml (app + PostgreSQL + nginx)
[ ] Write nginx.conf
[ ] Write gunicorn.conf.py
[ ] Build and test: docker compose up -d --build
[ ] Run migrations in container: docker compose exec app alembic upgrade head
[ ] Verify all endpoints work through nginx
[ ] Git commit: "Add Docker and nginx configuration"
```

### Phase 9: CI/CD

```
[ ] Write GitHub Actions workflow (.github/workflows/ci.yml)
    - Install deps
    - Run linter (ruff)
    - Run tests with coverage
    - Build Docker image
[ ] Push to GitHub
[ ] Verify CI passes
[ ] Git commit: "Add CI pipeline"
```

### Phase 10: Deployment

```
[ ] Choose deployment target (Render / Fly.io / VPS)
[ ] Configure production environment variables
[ ] Deploy
[ ] Verify health check
[ ] Test all endpoints against deployed version
[ ] Git commit: "Add deployment configuration"
```

### Phase 11: Documentation

```
[ ] Write README.md
    - Project description
    - Tech stack
    - Setup instructions (local and Docker)
    - API documentation link
    - Environment variables table
    - Running tests
[ ] Verify OpenAPI docs are complete and accurate
[ ] Git tag: v1.0.0
```

---

## API Specification

### Authentication

```
POST /api/v1/auth/register
  Body: {"username": "str", "email": "str", "password": "str"}
  Response: 201 UserResponse

POST /api/v1/auth/token
  Body: form-data (username, password)
  Response: 200 {"access_token": "str", "token_type": "bearer"}

GET /api/v1/auth/me
  Headers: Authorization: Bearer <token>
  Response: 200 UserResponse

PATCH /api/v1/auth/me
  Headers: Authorization: Bearer <token>
  Body: {"email": "str"} (partial)
  Response: 200 UserResponse

POST /api/v1/auth/change-password
  Headers: Authorization: Bearer <token>
  Body: {"current_password": "str", "new_password": "str"}
  Response: 200 {"message": "Password updated"}
```

### Tasks

```
POST /api/v1/tasks
  Headers: Authorization: Bearer <token>
  Body: TaskCreate
  Response: 201 TaskResponse

GET /api/v1/tasks
  Headers: Authorization: Bearer <token>
  Query: page, per_page, status, priority, search, sort_by, order
  Response: 200 TaskListResponse

GET /api/v1/tasks/stats
  Headers: Authorization: Bearer <token>
  Response: 200 TaskStats

GET /api/v1/tasks/{task_id}
  Headers: Authorization: Bearer <token>
  Response: 200 TaskResponse

PATCH /api/v1/tasks/{task_id}
  Headers: Authorization: Bearer <token>
  Body: TaskUpdate
  Response: 200 TaskResponse

DELETE /api/v1/tasks/{task_id}
  Headers: Authorization: Bearer <token>
  Response: 204 No Content
```

### Health

```
GET /health
  Response: 200 {"status": "healthy", "timestamp": "str", "version": "str"}

GET /health/ready
  Response: 200 {"status": "ready", "database": "connected"}
```

---

## Evaluation Criteria

Grade yourself against this rubric:

### Code Quality (25%)

- [ ] Clean project structure with separation of concerns
- [ ] Consistent naming conventions
- [ ] Type hints everywhere
- [ ] No hardcoded values
- [ ] No commented-out code
- [ ] No unused imports

### API Design (25%)

- [ ] RESTful URL patterns
- [ ] Correct HTTP methods and status codes
- [ ] Proper request/response validation
- [ ] Structured error responses
- [ ] Pagination on list endpoints
- [ ] No sensitive data in responses

### Testing (20%)

- [ ] Tests for happy paths and error cases
- [ ] Authentication tests
- [ ] Authorization tests (can't access other users' data)
- [ ] Edge case tests
- [ ] > 80% code coverage

### Infrastructure (15%)

- [ ] Docker works from clean state (`docker compose up -d --build`)
- [ ] Database migrations run cleanly
- [ ] Health checks pass
- [ ] Logging captures request lifecycle
- [ ] Environment-based configuration

### Git (15%)

- [ ] Meaningful commit messages
- [ ] Logical commit history (not one giant commit)
- [ ] .gitignore is correct
- [ ] No secrets in repository
- [ ] README is complete

---

## Stretch Goals

If you finish early and want more challenge:

1. **Refresh tokens** — Implement token refresh with shorter-lived access tokens and longer-lived refresh tokens
2. **Email notifications** — Send email when task is due (background task)
3. **Rate limiting** — Implement rate limiting middleware
4. **WebSocket** — Real-time task updates via WebSocket
5. **File attachments** — Upload files to tasks
6. **Admin dashboard** — Admin endpoints to manage all users and tasks
7. **API key authentication** — Alternative to JWT for machine-to-machine access
8. **Caching** — Add Redis caching for frequently-accessed data
9. **Full-text search** — PostgreSQL full-text search on tasks
10. **Monitoring** — Prometheus metrics endpoint

---

## What To Do When You Are Stuck

1. Re-read the relevant module
2. Check the FastAPI documentation: https://fastapi.tiangolo.com
3. Check the SQLAlchemy documentation: https://docs.sqlalchemy.org
4. Read the error message completely
5. Add logging around the failing code
6. Write a minimal reproduction
7. Search the error message (with quotes)
8. Take a break. Seriously. Complex bugs often solve themselves after rest.

---

## After the Capstone

You have now built a production-ready API from first principles. You understand:

- How the internet works at a protocol level
- How to design RESTful APIs
- How to navigate Linux systems
- How to use Git professionally
- How to build, test, and deploy FastAPI applications
- How to authenticate users and protect resources
- How to work with databases
- How to containerize and deploy applications

**Next steps to continue growing:**

- Build a frontend that consumes your API (React, Vue, or HTMX)
- Learn about message queues (RabbitMQ, Celery)
- Study system design (load balancing, caching, database scaling)
- Contribute to open-source FastAPI projects
- Build another project from scratch — repetition builds mastery

---

*Congratulations. You are no longer a beginner.*
