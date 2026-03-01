# Module 12: Deployment and Production

## Learning Objectives

By the end of this module, you will be able to:

- Containerize a FastAPI application with Docker
- Write a production-quality Dockerfile
- Use Docker Compose for multi-service setups
- Configure a reverse proxy with nginx
- Deploy to a cloud provider
- Set up environment-based configuration
- Implement health checks and monitoring basics
- Understand production vs development differences

---

## 12.1 Development vs Production

| Aspect | Development | Production |
|--------|-------------|------------|
| Server | `uvicorn --reload` | gunicorn + uvicorn workers |
| Database | SQLite | PostgreSQL |
| Debug mode | On | Off |
| CORS | Permissive | Strict |
| HTTPS | No | Required |
| Logging | Debug level | Info/Warning |
| Secrets | `.env` file | Environment variables / secrets manager |
| Errors | Full traceback | Generic message |
| Data | Test data | Real data |
| Monitoring | None | Metrics, alerts, logs |

---

## 12.2 Docker Fundamentals

### What Docker Does

Docker packages your application and all its dependencies into a **container** — a lightweight, isolated environment that runs the same everywhere.

```
"It works on my machine" → "It works in the container" → "It works everywhere"
```

### Key Concepts

```
Dockerfile    → Recipe to build an image
Image         → Snapshot of your application + dependencies (like a class)
Container     → Running instance of an image (like an object)
Registry      → Where images are stored (Docker Hub, ECR, etc.)
```

```
┌──────────────────────────────────────────┐
│              Docker Host                  │
│                                          │
│  ┌────────────┐  ┌────────────┐         │
│  │ Container 1│  │ Container 2│         │
│  │  FastAPI   │  │ PostgreSQL │         │
│  │  :8000     │  │  :5432     │         │
│  └────────────┘  └────────────┘         │
│                                          │
│  Shared kernel, isolated filesystems     │
└──────────────────────────────────────────┘
```

### Install Docker

```bash
# macOS / Windows: Download Docker Desktop
# https://www.docker.com/products/docker-desktop

# Linux:
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Verify
docker --version
docker compose version
```

---

## 12.3 Dockerizing FastAPI

### Dockerfile

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Why This Dockerfile Is Structured This Way

```
FROM python:3.12-slim          ← Small base image (not full python:3.12)
COPY requirements.txt .        ← Copy deps file FIRST
RUN pip install ...            ← Install deps (cached if requirements.txt unchanged)
COPY . .                       ← Copy code AFTER deps (code changes often, deps don't)
USER appuser                   ← Never run as root in production
EXPOSE 8000                    ← Document the port (doesn't actually open it)
CMD [...]                      ← Default command when container starts
```

### .dockerignore

```
# .dockerignore
.venv/
__pycache__/
*.pyc
.git/
.gitignore
.env
*.db
*.sqlite3
tests/
htmlcov/
.coverage
.pytest_cache/
docker-compose*.yml
Dockerfile
README.md
```

### Build and Run

```bash
# Build the image
docker build -t task-manager .

# Run the container
docker run -d \
  --name task-manager \
  -p 8000:8000 \
  -e DATABASE_URL="sqlite+aiosqlite:///./data/app.db" \
  -e SECRET_KEY="your-production-secret" \
  task-manager

# Verify
curl http://localhost:8000/health

# View logs
docker logs task-manager
docker logs -f task-manager    # Follow

# Stop and remove
docker stop task-manager
docker rm task-manager

# List running containers
docker ps

# List all containers (including stopped)
docker ps -a

# List images
docker images
```

---

## 12.4 Docker Compose — Multi-Service Setup

For running multiple services together (app + database + cache, etc.).

```yaml
# docker-compose.yml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/taskmanager
      - SECRET_KEY=change-this-in-production
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=taskmanager
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
    depends_on:
      - app
    restart: unless-stopped

volumes:
  postgres_data:
```

### nginx Configuration

```nginx
# nginx.conf
upstream fastapi {
    server app:8000;
}

server {
    listen 80;
    server_name localhost;

    location / {
        proxy_pass http://fastapi;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90;
    }

    location /health {
        proxy_pass http://fastapi/health;
    }
}
```

### Docker Compose Commands

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f
docker compose logs -f app     # Just the app

# Stop all services
docker compose down

# Stop and remove volumes (deletes database data)
docker compose down -v

# Rebuild after code changes
docker compose up -d --build

# Run a command in a container
docker compose exec app alembic upgrade head
docker compose exec db psql -U postgres -d taskmanager
```

---

## 12.5 Production Server Configuration

### gunicorn with uvicorn Workers

For production, use gunicorn as the process manager with uvicorn workers:

```bash
pip install gunicorn
```

```python
# gunicorn.conf.py
import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
```

```dockerfile
# Production CMD in Dockerfile
CMD ["gunicorn", "app.main:app", "-c", "gunicorn.conf.py"]
```

### Why gunicorn?

```
uvicorn alone:
  └── 1 process, 1 event loop → limited by one CPU core

gunicorn + uvicorn workers:
  └── gunicorn (master)
       ├── uvicorn worker 1 (process 1, event loop)
       ├── uvicorn worker 2 (process 2, event loop)
       ├── uvicorn worker 3 (process 3, event loop)
       └── uvicorn worker 4 (process 4, event loop)

  → Uses ALL CPU cores
  → Worker crashes → gunicorn restarts it
  → Graceful reloads during deployment
```

---

## 12.6 Environment Configuration

```python
# app/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "Task Manager API"
    debug: bool = False

    database_url: str
    secret_key: str

    access_token_expire_minutes: int = 30
    allowed_origins: list[str] = ["http://localhost:3000"]

    log_level: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```bash
# .env.example (committed to Git — shows required variables)
DATABASE_URL=sqlite+aiosqlite:///./taskmanager.db
SECRET_KEY=change-me-to-a-real-secret
DEBUG=true
ALLOWED_ORIGINS=["http://localhost:3000"]
LOG_LEVEL=DEBUG
```

---

## 12.7 Health Checks

Every production service needs health checks.

```python
from datetime import datetime
from sqlalchemy import text

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
    }

@app.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)):
    """Check if the app can handle requests (database connected)."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "database": str(e)},
        )
```

Load balancers and orchestrators (Kubernetes, ECS) use these endpoints to:
- Know when the container is ready to receive traffic
- Detect unhealthy containers and restart them
- Route traffic away from failing instances

---

## 12.8 Deployment Options

### Option A: Cloud VPS (DigitalOcean, Linode, Hetzner)

```bash
# On the VPS
sudo apt update && sudo apt install -y docker.io docker-compose-v2

# Clone your repo
git clone https://github.com/you/task-manager.git
cd task-manager

# Create production .env
nano .env

# Start
docker compose up -d

# Set up TLS with Let's Encrypt (via certbot or Caddy)
```

**Cost:** $5-10/month. Full control. Good for learning.

### Option B: Platform as a Service (Render, Railway, Fly.io)

```bash
# Fly.io example
flyctl launch
flyctl secrets set SECRET_KEY=your-secret DATABASE_URL=postgres://...
flyctl deploy
```

**Cost:** Free tier available. Less control. Fastest to deploy.

### Option C: Cloud Provider (AWS, GCP, Azure)

AWS architecture for a production API:

```
Internet
  │
  ▼
Route 53 (DNS)
  │
  ▼
Application Load Balancer (HTTPS termination)
  │
  ▼
ECS Fargate (containers) ──► RDS PostgreSQL
  │
  ▼
CloudWatch (logs + monitoring)
```

**Cost:** Variable. Most control. Most complex.

---

## 12.9 Deployment Checklist

```
Pre-deployment:
  [ ] All tests pass
  [ ] No hardcoded secrets in code
  [ ] .env.example documents all required variables
  [ ] Database migrations are committed
  [ ] Dockerfile builds successfully
  [ ] Docker Compose starts cleanly from scratch
  [ ] Health check endpoints work

Configuration:
  [ ] DEBUG = False
  [ ] SECRET_KEY is random and long (64+ chars)
  [ ] DATABASE_URL points to production database
  [ ] CORS origins are specific (not *)
  [ ] HTTPS is configured
  [ ] Log level is INFO or WARNING

Infrastructure:
  [ ] Reverse proxy (nginx) in front of app server
  [ ] Database has backups enabled
  [ ] TLS certificate is valid and auto-renewing
  [ ] Health checks are configured in load balancer
  [ ] Log aggregation is set up
  [ ] Monitoring/alerting for errors and latency

Post-deployment:
  [ ] Health check returns 200
  [ ] Can create/read/update/delete resources
  [ ] Authentication works
  [ ] Logs are flowing
  [ ] No errors in first 10 minutes
```

---

## 12.10 CI/CD Overview

Continuous Integration / Continuous Deployment automates testing and deployment.

```
Developer pushes code
       │
       ▼
┌─────────────────┐
│   CI Pipeline   │
│                 │
│ 1. Install deps │
│ 2. Run linter   │
│ 3. Run tests    │
│ 4. Build Docker │
│    image        │
└────────┬────────┘
         │ (if all pass)
         ▼
┌─────────────────┐
│   CD Pipeline   │
│                 │
│ 1. Push image   │
│    to registry  │
│ 2. Deploy to    │
│    staging      │
│ 3. Run smoke    │
│    tests        │
│ 4. Deploy to    │
│    production   │
└─────────────────┘
```

### GitHub Actions Example

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_taskmanager
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run linter
        run: ruff check .

      - name: Run tests
        env:
          DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/test_taskmanager
          SECRET_KEY: test-secret-key
        run: pytest --cov=app --cov-report=term-missing

      - name: Build Docker image
        run: docker build -t task-manager .
```

---

## Checkpoint Quiz

1. What is the difference between a Docker image and a container?
2. Why does the Dockerfile copy `requirements.txt` before the rest of the code?
3. What does `docker compose up -d` do?
4. Why use gunicorn with uvicorn workers instead of just uvicorn?
5. What is the purpose of a health check endpoint?
6. Why should you never run containers as root?
7. What does a reverse proxy do in production?
8. What goes in `.env.example` vs `.env`?
9. What is CI/CD?
10. What is the first thing to check after deploying?

---

## Common Mistakes

1. **Running as root in Docker.** Always create and use a non-root user.
2. **Using `latest` tag for base images.** Pin versions: `python:3.12-slim`, not `python:latest`.
3. **Not using `.dockerignore`.** Without it, your `.venv`, `.git`, and tests get copied into the image.
4. **Hardcoding configuration.** All config must come from environment variables.
5. **No health checks.** Without them, your load balancer can't tell if your app is alive.
6. **Exposing the database to the internet.** Only the app container should connect to the database.
7. **Not setting up logging.** When production breaks, logs are your only debugging tool.
8. **Deploying without testing.** CI must pass before deployment. No exceptions.

---

## Exercise: Deploy the Task Manager

1. Write a production Dockerfile
2. Create a `docker-compose.yml` with app + PostgreSQL + nginx
3. Configure nginx as a reverse proxy
4. Run the full stack locally with Docker Compose
5. Run database migrations inside the container
6. Verify all endpoints work through nginx
7. (Optional) Deploy to a free tier on Render or Fly.io

---

## Next Module

Proceed to `capstone_project.md` →
