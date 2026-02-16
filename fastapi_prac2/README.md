# FastAPI Practice Project

A production-ready FastAPI project structure for learning and practicing backend development.

## Project Structure

```
fastapi_prac2/
├── app/
│   ├── core/           # Config, database, security, exceptions
│   ├── models/         # SQLAlchemy ORM models
│   ├── schemas/        # Pydantic schemas
│   ├── repositories/   # Data access layer
│   ├── services/       # Business logic layer
│   ├── routes/         # API endpoints
│   └── main.py         # FastAPI app
├── tests/
│   ├── unit/
│   └── integration/
├── alembic/            # Database migrations
├── requirements.txt
└── .env
```

## Quick Start

### 1. Activate Virtual Environment

```bash
cd fastapi_prac2
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Create Database Tables

```bash
python -c "
import asyncio
from app.core.database import engine, Base
from app.models import User, Item

async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Tables created!')

asyncio.run(init())
"
```

### 4. Run the Server

```bash
uvicorn app.main:app --reload
```

Or:

```bash
python -m app.main
```

### 5. Open API Docs

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## API Endpoints

### Authentication
- `POST /auth/register` - Register new user
- `POST /auth/token` - Login (get JWT token)

### Users
- `GET /users/me` - Get current user profile
- `PATCH /users/me` - Update current user
- `GET /users/` - List all users (auth required)
- `GET /users/{id}` - Get user by ID

### Items
- `POST /items/` - Create item (auth required)
- `GET /items/` - List all items (public)
- `GET /items/my` - List my items (auth required)
- `GET /items/{id}` - Get item by ID
- `PATCH /items/{id}` - Update item (owner only)
- `DELETE /items/{id}` - Delete item (owner only)

## Testing the API

### 1. Register a User

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "username": "testuser", "password": "Password123"}'
```

### 2. Login

```bash
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=Password123"
```

### 3. Use Token for Authenticated Requests

```bash
curl http://localhost:8000/users/me \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## Practice Ideas

1. **Add pagination** to list endpoints
2. **Implement search/filtering** for items
3. **Add categories** to items (new model with relationships)
4. **Implement soft delete** instead of hard delete
5. **Add rate limiting** middleware
6. **Write unit tests** for services
7. **Write integration tests** for routes
8. **Add background tasks** (e.g., send email on registration)
9. **Implement caching** with Redis
10. **Add Alembic migrations** for schema changes

## Architecture Patterns Used

- **Repository Pattern**: Data access abstraction
- **Service Layer**: Business logic separation
- **Dependency Injection**: FastAPI's Depends()
- **DTO Pattern**: Pydantic schemas for data transfer
- **Clean Architecture**: Routes → Services → Repositories → Database

Happy coding!
