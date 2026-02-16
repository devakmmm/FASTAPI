# File: backend_fastapi_mastery/13_scalability_and_deployment.md

# Scalability and Deployment

## Understanding Scalability

**Vertical Scaling (Scale Up)**: Bigger machine
- More CPU, RAM
- Limited by hardware
- Simple but expensive

**Horizontal Scaling (Scale Out)**: More machines
- Add more instances
- Theoretically unlimited
- Requires stateless design

```
Vertical Scaling:
┌─────────────────────┐
│     BIG SERVER      │
│  CPU: 64 cores      │
│  RAM: 256GB         │
└─────────────────────┘

Horizontal Scaling:
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ Server 1│ │ Server 2│ │ Server 3│ │ Server 4│
└─────────┘ └─────────┘ └─────────┘ └─────────┘
      ↑           ↑           ↑           ↑
      └───────────┴───────────┴───────────┘
                       │
                ┌──────┴──────┐
                │Load Balancer│
                └─────────────┘
```

---

## Uvicorn vs Gunicorn

### Uvicorn (ASGI Server)

```bash
# Development
uvicorn main:app --reload

# Production (single process)
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Uvicorn alone:**
- Single process by default
- `--workers` adds multiple processes
- Each worker is independent
- Good for Docker/K8s (let orchestrator manage processes)

### Gunicorn + Uvicorn Workers

```bash
# Production (multiple workers managed by Gunicorn)
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

**Gunicorn with Uvicorn workers:**
- Gunicorn manages worker processes
- Each worker runs Uvicorn
- Graceful restarts/reloads
- Better process management
- Traditional deployment model

### Configuration

```python
# gunicorn.conf.py
import multiprocessing

# Bind
bind = "0.0.0.0:8000"

# Workers
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"

# Timeouts
timeout = 120
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process naming
proc_name = "myapp"

# Security
limit_request_line = 4096
limit_request_fields = 100
```

### Workers Calculation

```python
# Rule of thumb
workers = (2 * cpu_cores) + 1

# For I/O bound (most APIs)
workers = cpu_cores * 2  # Or more

# For CPU bound
workers = cpu_cores

# Docker/Kubernetes: Often use fewer workers
# Let the orchestrator scale pods instead
workers = 2  # And scale pods
```

---

## Docker Configuration

### Dockerfile

```dockerfile
# Multi-stage build for smaller image
FROM python:3.11-slim as builder

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Create non-root user
RUN useradd --create-home --shell /bin/bash app
USER app

# Copy dependencies from builder
COPY --from=builder /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH

# Copy application code
COPY --chown=app:app . .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/myapp
      - REDIS_URL=redis://redis:6379
      - ENVIRONMENT=production
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 512M

  db:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=myapp
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d myapp"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - api

volumes:
  postgres_data:
  redis_data:
```

---

## Environment Configuration

### Settings Pattern

```python
# core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "MyApp"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    
    # Database
    DATABASE_URL: str
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    
    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # External Services
    STRIPE_API_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

### Environment-Specific Config

```python
# Load based on environment
class DevelopmentSettings(Settings):
    DEBUG: bool = True
    DB_POOL_SIZE: int = 2

class ProductionSettings(Settings):
    DEBUG: bool = False
    DB_POOL_SIZE: int = 20

class TestSettings(Settings):
    DEBUG: bool = True
    DATABASE_URL: str = "sqlite+aiosqlite:///:memory:"

def get_settings() -> Settings:
    env = os.getenv("ENVIRONMENT", "development")
    
    if env == "production":
        return ProductionSettings()
    elif env == "test":
        return TestSettings()
    else:
        return DevelopmentSettings()
```

---

## Kubernetes Deployment

### Deployment Manifest

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: fastapi-app
  template:
    metadata:
      labels:
        app: fastapi-app
    spec:
      containers:
      - name: app
        image: myregistry/fastapi-app:latest
        ports:
        - containerPort: 8000
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: database-url
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 15
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
```

### Service and Ingress

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: fastapi-app
spec:
  selector:
    app: fastapi-app
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP

---
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: fastapi-app
  annotations:
    nginx.ingress.kubernetes.io/rate-limit: "100"
spec:
  rules:
  - host: api.myapp.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: fastapi-app
            port:
              number: 80
```

### Horizontal Pod Autoscaler

```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: fastapi-app
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: fastapi-app
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

---

## Production Readiness Checklist

### Configuration
- [ ] Environment variables for all secrets
- [ ] No hardcoded credentials
- [ ] Proper database connection pooling
- [ ] Timeouts configured for all external calls

### Security
- [ ] HTTPS enforced
- [ ] Security headers configured
- [ ] CORS properly restricted
- [ ] Input validation on all endpoints
- [ ] Rate limiting implemented
- [ ] Authentication/authorization tested

### Observability
- [ ] Structured logging
- [ ] Request ID tracking
- [ ] Metrics exposed (Prometheus)
- [ ] Health check endpoints
- [ ] Error tracking (Sentry)
- [ ] Distributed tracing

### Performance
- [ ] Database queries optimized (no N+1)
- [ ] Proper indexing
- [ ] Caching where appropriate
- [ ] Async where beneficial
- [ ] Connection pooling

### Reliability
- [ ] Graceful shutdown handling
- [ ] Circuit breakers for external services
- [ ] Retry logic with backoff
- [ ] Dead letter queues for failed jobs
- [ ] Database migrations tested

### Operations
- [ ] Docker image builds
- [ ] CI/CD pipeline
- [ ] Rollback procedure documented
- [ ] Runbook for common issues
- [ ] Alerting configured
- [ ] Backup and recovery tested

---

## Scaling Patterns

### Stateless Application

```python
# DON'T: Store state in memory
class App:
    def __init__(self):
        self.user_sessions = {}  # Lost when pod restarts/scales!

# DO: Store state externally
async def get_session(session_id: str) -> Session:
    return await redis.get(f"session:{session_id}")

async def set_session(session_id: str, data: dict):
    await redis.set(f"session:{session_id}", json.dumps(data), ex=3600)
```

### Database Connection Pooling

```python
# Configure for your replica count
# If you have 10 pods, each with pool_size=10, that's 100 connections!
# Most databases max at 100-500 connections

PODS = int(os.getenv("REPLICA_COUNT", 3))
MAX_DB_CONNECTIONS = 100

engine = create_async_engine(
    DATABASE_URL,
    pool_size=max(5, MAX_DB_CONNECTIONS // PODS),
    max_overflow=5
)
```

### Caching Strategy

```python
# Cache responses for read-heavy endpoints
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from fastapi_cache.backends.redis import RedisBackend

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = await aioredis.from_url(REDIS_URL)
    FastAPICache.init(RedisBackend(redis), prefix="cache:")
    yield
    await redis.close()

@app.get("/products")
@cache(expire=60)  # Cache for 60 seconds
async def list_products():
    return await db.query(Product).all()
```

### Read Replicas

```python
# Route reads to replicas, writes to primary
write_engine = create_async_engine(PRIMARY_DB_URL)
read_engine = create_async_engine(REPLICA_DB_URL)

WriteSession = sessionmaker(write_engine, class_=AsyncSession)
ReadSession = sessionmaker(read_engine, class_=AsyncSession)

@app.get("/products")
async def list_products():
    async with ReadSession() as session:  # Read from replica
        return await session.query(Product).all()

@app.post("/products")
async def create_product(product: ProductCreate):
    async with WriteSession() as session:  # Write to primary
        ...
```

---

## Graceful Shutdown

```python
import signal
from contextlib import asynccontextmanager

shutdown_event = asyncio.Event()

def signal_handler():
    shutdown_event.set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    # Startup
    await startup()
    
    yield
    
    # Shutdown
    logger.info("Shutdown signal received")
    
    # Stop accepting new requests (handled by server)
    
    # Wait for in-flight requests (give them time)
    await asyncio.sleep(5)
    
    # Close connections
    await database.disconnect()
    await redis.close()
    await http_client.aclose()
    
    logger.info("Shutdown complete")
```

---

## Mastery Checkpoints

### Conceptual Questions

1. **Why use Gunicorn with Uvicorn workers instead of just Uvicorn?**

   *Answer*: Gunicorn provides better process management - graceful restarts, worker recycling, signal handling. Uvicorn alone is simpler but lacks these features. In Kubernetes, you might use Uvicorn alone since K8s handles process management via pod lifecycle.

2. **How do you determine the right number of workers?**

   *Answer*: For I/O bound (typical API): 2×CPU + 1 is a starting point. For CPU bound: match CPU cores. In containers, consider total cluster connections - 10 pods × 10 workers = 100 database connections. Monitor and adjust based on actual load patterns.

3. **What makes an application "stateless" for horizontal scaling?**

   *Answer*: No in-memory state that persists across requests. All state stored externally (database, Redis, object storage). Any instance can handle any request. Session data, file uploads, job queues - all external. This allows adding/removing instances freely.

4. **How do liveness and readiness probes differ?**

   *Answer*: Liveness: "Is the process healthy?" Failure triggers restart. Readiness: "Can it serve traffic?" Failure removes from load balancer but doesn't restart. Example: DB disconnected - readiness fails (stop traffic) but liveness passes (don't restart, DB will reconnect).

5. **Why is graceful shutdown important?**

   *Answer*: Without it, in-flight requests are terminated, causing errors. Connections to databases/caches aren't properly closed, potentially causing issues. Graceful shutdown: stop accepting new requests, finish in-flight ones, close connections cleanly, then exit.

### Scenario Questions

6. **Your API handles 100 req/s. You need to scale to 1000 req/s. What's your approach?**

   *Answer*:
   1. Profile current bottlenecks (CPU? DB? external APIs?)
   2. Add caching for read-heavy endpoints (reduce DB load 10x)
   3. Optimize slow queries (indexes, eager loading)
   4. Scale horizontally (10 pods instead of 1)
   5. Add read replicas if DB is bottleneck
   6. Consider CDN for static assets
   7. Async processing for non-critical work
   8. Load test to verify 1000 req/s achieved

7. **Your app runs fine with 1 pod but fails with 3 pods. What could be wrong?**

   *Answer*: Likely state issues:
   - In-memory sessions (use Redis)
   - File uploads to local disk (use S3)
   - Assuming sequential request handling
   - Race conditions with concurrent access
   - Database connection limits exceeded (100 connections, 3 pods × 40 = 120!)
   - Cron jobs running on every pod (use distributed lock)

8. **Design deployment strategy for zero-downtime updates.**

   *Answer*:
   ```yaml
   spec:
     replicas: 3
     strategy:
       type: RollingUpdate
       rollingUpdate:
         maxSurge: 1        # Add 1 new pod
         maxUnavailable: 0  # Never reduce below 3
   ```
   
   Plus:
   - Readiness probe ensures traffic only goes to ready pods
   - New pods start, become ready, then old pods terminate
   - Database migrations must be backward compatible
   - Feature flags for breaking changes

9. **How do you handle secrets in production?**

   *Answer*:
   - Never in code or Docker images
   - Kubernetes Secrets or external secret manager (Vault, AWS Secrets Manager)
   - Inject via environment variables or mounted files
   - Rotate secrets without redeployment (external manager)
   - Audit secret access
   ```yaml
   env:
   - name: DATABASE_URL
     valueFrom:
       secretKeyRef:
         name: app-secrets
         key: database-url
   ```

10. **Your API is slow under load. Walk through debugging approach.**

    *Answer*:
    1. Check metrics: CPU, memory, request latency
    2. Check logs for errors or slow operations
    3. Profile: Where is time spent?
       - Database queries: Check query logs, add indexes
       - External APIs: Add caching, circuit breakers
       - CPU-bound: Optimize or offload to workers
    4. Check connection pools: Are they exhausted?
    5. Check async: Any blocking calls in async context?
    6. Load test specific endpoints to isolate
    7. Scale if needed, but fix root cause first

---

## Interview Framing

When discussing deployment:

1. **Show operational awareness**: "I configure health checks, graceful shutdown, and proper resource limits. In Kubernetes, I use readiness probes to ensure traffic only goes to healthy pods."

2. **Discuss scaling strategy**: "I design stateless from the start - all state in Redis or database. This lets me scale horizontally without code changes. Connection pooling is sized for the total cluster, not per-pod."

3. **Explain deployment process**: "I use rolling updates with zero downtime. Database migrations are backward compatible so old and new code can run together. Feature flags let me deploy code before enabling features."

4. **Connect to observability**: "I can't scale what I can't measure. Prometheus metrics show request rate, latency, and resource usage. Alerts fire before users notice problems. I watch metrics during deployments."

5. **Mention practical experience**: "I've dealt with scale issues - connection pool exhaustion when we added pods, memory leaks causing OOM kills, slow queries that only appeared under load. Each taught me something about production systems."
