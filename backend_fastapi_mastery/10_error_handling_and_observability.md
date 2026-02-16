# File: backend_fastapi_mastery/10_error_handling_and_observability.md

# Error Handling and Observability

## Why Observability Matters

When your API is running in production at 3 AM and something breaks:
- Can you tell *what* broke?
- Can you tell *why* it broke?
- Can you trace a single request across services?
- Can you see the error *before* users complain?

Observability isn't logging. It's building systems that explain themselves.

---

## The Three Pillars of Observability

### 1. Logs: What Happened

Discrete events with context.

### 2. Metrics: How Much

Aggregated numbers over time.

### 3. Traces: Where

Request flow across services.

```
User Request
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Your API                                  │
│                                                                 │
│  LOGS: "User 123 requested /orders, took 250ms, returned 200"  │
│                                                                 │
│  METRICS: request_count++, latency_histogram.observe(0.25)     │
│                                                                 │
│  TRACES: trace_id=abc123 → auth_service → database → response  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Structured Logging

### Why Structured?

```python
# WRONG: Unstructured logs - good luck parsing these
logger.info(f"User {user_id} created order {order_id} for ${amount}")
logger.error(f"Payment failed for user {user_id}: {error}")

# RIGHT: Structured logs - machine parseable, searchable
logger.info("Order created", extra={
    "user_id": user_id,
    "order_id": order_id,
    "amount": amount,
    "currency": "USD"
})
logger.error("Payment failed", extra={
    "user_id": user_id,
    "error_type": type(error).__name__,
    "error_message": str(error),
    "payment_provider": "stripe"
})
```

### Production Logging Setup

```python
import logging
import json
from datetime import datetime
from typing import Any

class JSONFormatter(logging.Formatter):
    """Format logs as JSON for log aggregation systems"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "trace_id"):
            log_data["trace_id"] = record.trace_id
        
        # Add any extra attributes
        for key, value in record.__dict__.items():
            if key not in ["name", "msg", "args", "created", "filename", 
                          "funcName", "levelname", "levelno", "lineno",
                          "module", "msecs", "pathname", "process",
                          "processName", "relativeCreated", "stack_info",
                          "exc_info", "exc_text", "thread", "threadName"]:
                log_data[key] = value
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)

def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    
    # Reduce noise from libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

# Call at startup
setup_logging()
```

### Request Context Logging

```python
import contextvars
from uuid import uuid4

# Context variables for request-scoped data
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id")
user_id_var: contextvars.ContextVar[int | None] = contextvars.ContextVar("user_id", default=None)

class ContextLogger:
    """Logger that automatically includes request context"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _add_context(self, extra: dict) -> dict:
        extra = extra or {}
        try:
            extra["request_id"] = request_id_var.get()
        except LookupError:
            pass
        try:
            user_id = user_id_var.get()
            if user_id:
                extra["user_id"] = user_id
        except LookupError:
            pass
        return extra
    
    def info(self, msg: str, **kwargs):
        self.logger.info(msg, extra=self._add_context(kwargs))
    
    def error(self, msg: str, **kwargs):
        self.logger.error(msg, extra=self._add_context(kwargs))
    
    def warning(self, msg: str, **kwargs):
        self.logger.warning(msg, extra=self._add_context(kwargs))

logger = ContextLogger(__name__)
```

---

## Request ID / Trace ID Middleware

```python
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from uuid import uuid4
import time

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request_id_var.set(request_id)
        
        # Store in request state for access in routes
        request.state.request_id = request_id
        
        # Log request start
        logger.info("Request started", 
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host
        )
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Log request completion
            duration = time.time() - start_time
            logger.info("Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2)
            )
            
            # Add request ID to response
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error("Request failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration_ms=round(duration * 1000, 2)
            )
            raise

app.add_middleware(RequestContextMiddleware)
```

---

## Exception Handling

### Custom Exception Hierarchy

```python
# core/exceptions.py
class AppException(Exception):
    """Base exception for application errors"""
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    
    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

class NotFoundError(AppException):
    status_code = 404
    error_code = "NOT_FOUND"

class ValidationError(AppException):
    status_code = 400
    error_code = "VALIDATION_ERROR"

class ConflictError(AppException):
    status_code = 409
    error_code = "CONFLICT"

class AuthenticationError(AppException):
    status_code = 401
    error_code = "AUTHENTICATION_ERROR"

class AuthorizationError(AppException):
    status_code = 403
    error_code = "AUTHORIZATION_ERROR"

class RateLimitError(AppException):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"

class ExternalServiceError(AppException):
    status_code = 502
    error_code = "EXTERNAL_SERVICE_ERROR"
```

### Global Exception Handlers

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

def create_error_response(
    request_id: str,
    error_code: str,
    message: str,
    details: dict = None
) -> dict:
    return {
        "error": {
            "code": error_code,
            "message": message,
            "details": details or {},
            "request_id": request_id
        }
    }

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.error("Application error",
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            request_id=request_id,
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details
        )
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Transform Pydantic errors to user-friendly format
    details = []
    for error in exc.errors():
        details.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    logger.warning("Validation error", validation_errors=details)
    
    return JSONResponse(
        status_code=422,
        content=create_error_response(
            request_id=request_id,
            error_code="VALIDATION_ERROR",
            message="Request validation failed",
            details={"errors": details}
        )
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    request_id = getattr(request.state, "request_id", "unknown")
    
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            request_id=request_id,
            error_code=f"HTTP_{exc.status_code}",
            message=exc.detail
        )
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Log full traceback for debugging
    logger.exception("Unhandled exception",
        error_type=type(exc).__name__,
        error_message=str(exc)
    )
    
    # Don't expose internal details to client
    return JSONResponse(
        status_code=500,
        content=create_error_response(
            request_id=request_id,
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred. Please try again later."
        )
    )
```

---

## Metrics

### Using Prometheus

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import Response

# Define metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

ACTIVE_REQUESTS = Gauge(
    "http_requests_active",
    "Active HTTP requests"
)

DB_POOL_SIZE = Gauge(
    "db_pool_connections",
    "Database pool connections",
    ["state"]  # idle, active
)

EXTERNAL_API_CALLS = Counter(
    "external_api_calls_total",
    "External API calls",
    ["service", "endpoint", "status"]
)

EXTERNAL_API_LATENCY = Histogram(
    "external_api_latency_seconds",
    "External API latency",
    ["service", "endpoint"]
)
```

### Metrics Middleware

```python
import time
from starlette.middleware.base import BaseHTTPMiddleware

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ACTIVE_REQUESTS.inc()
        
        # Normalize endpoint for metrics (avoid high cardinality)
        endpoint = self._normalize_path(request.url.path)
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=endpoint,
                status=response.status_code
            ).inc()
            
            REQUEST_LATENCY.labels(
                method=request.method,
                endpoint=endpoint
            ).observe(time.time() - start_time)
            
            return response
        finally:
            ACTIVE_REQUESTS.dec()
    
    def _normalize_path(self, path: str) -> str:
        """Normalize path to avoid high cardinality metrics"""
        # /users/123 -> /users/{id}
        # /orders/abc-def -> /orders/{id}
        parts = path.split("/")
        normalized = []
        for part in parts:
            if part.isdigit() or self._looks_like_uuid(part):
                normalized.append("{id}")
            else:
                normalized.append(part)
        return "/".join(normalized)
    
    @staticmethod
    def _looks_like_uuid(s: str) -> bool:
        return len(s) == 36 and s.count("-") == 4

app.add_middleware(MetricsMiddleware)

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )
```

### Business Metrics

```python
ORDERS_CREATED = Counter(
    "orders_created_total",
    "Total orders created",
    ["payment_method", "status"]
)

ORDER_VALUE = Histogram(
    "order_value_dollars",
    "Order value distribution",
    buckets=[10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
)

async def create_order(order: OrderCreate) -> Order:
    result = await order_service.create(order)
    
    # Record business metrics
    ORDERS_CREATED.labels(
        payment_method=order.payment_method,
        status="created"
    ).inc()
    
    ORDER_VALUE.observe(float(result.total))
    
    return result
```

---

## Distributed Tracing

### OpenTelemetry Setup

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

def setup_tracing(app: FastAPI, service_name: str):
    # Configure provider
    provider = TracerProvider()
    
    # Export to collector (e.g., Jaeger, Zipkin)
    exporter = OTLPSpanExporter(endpoint="http://collector:4317")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    
    trace.set_tracer_provider(provider)
    
    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    # Auto-instrument HTTP client
    HTTPXClientInstrumentor().instrument()
    
    # Auto-instrument database
    SQLAlchemyInstrumentor().instrument(engine=engine)

# Get tracer for custom spans
tracer = trace.get_tracer(__name__)
```

### Custom Spans

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def process_payment(payment: PaymentRequest):
    with tracer.start_as_current_span("process_payment") as span:
        span.set_attribute("payment.amount", payment.amount)
        span.set_attribute("payment.currency", payment.currency)
        
        # Child span for validation
        with tracer.start_as_current_span("validate_payment"):
            await validate_payment(payment)
        
        # Child span for external API
        with tracer.start_as_current_span("stripe_api_call") as stripe_span:
            stripe_span.set_attribute("stripe.customer_id", payment.customer_id)
            
            try:
                result = await stripe_client.create_charge(payment)
                stripe_span.set_attribute("stripe.charge_id", result.id)
            except StripeError as e:
                stripe_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise
        
        return result
```

### Trace Context Propagation

```python
from opentelemetry import trace
from opentelemetry.propagate import inject, extract

async def call_downstream_service(data: dict):
    headers = {}
    
    # Inject trace context into headers
    inject(headers)
    
    # Headers now contain traceparent, tracestate
    response = await http_client.post(
        "http://downstream-service/api",
        json=data,
        headers=headers
    )
    
    return response

# In downstream service
@app.post("/api")
async def handle_request(request: Request):
    # Extract trace context from headers
    context = extract(dict(request.headers))
    
    with tracer.start_as_current_span("handle_request", context=context):
        # This span is linked to the parent trace
        pass
```

---

## Health Checks

### Comprehensive Health Endpoint

```python
from enum import Enum
from pydantic import BaseModel

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

class ComponentHealth(BaseModel):
    status: HealthStatus
    latency_ms: float | None = None
    message: str | None = None

class HealthResponse(BaseModel):
    status: HealthStatus
    components: dict[str, ComponentHealth]
    version: str

async def check_database() -> ComponentHealth:
    start = time.time()
    try:
        async with db.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return ComponentHealth(
            status=HealthStatus.HEALTHY,
            latency_ms=round((time.time() - start) * 1000, 2)
        )
    except Exception as e:
        return ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=str(e)
        )

async def check_redis() -> ComponentHealth:
    start = time.time()
    try:
        await redis.ping()
        return ComponentHealth(
            status=HealthStatus.HEALTHY,
            latency_ms=round((time.time() - start) * 1000, 2)
        )
    except Exception as e:
        return ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=str(e)
        )

async def check_stripe() -> ComponentHealth:
    start = time.time()
    try:
        # Light API call to verify connectivity
        await stripe_client.get_balance()
        return ComponentHealth(
            status=HealthStatus.HEALTHY,
            latency_ms=round((time.time() - start) * 1000, 2)
        )
    except Exception as e:
        return ComponentHealth(
            status=HealthStatus.DEGRADED,  # Not critical
            message=str(e)
        )

@app.get("/health", response_model=HealthResponse)
async def health_check():
    checks = await asyncio.gather(
        check_database(),
        check_redis(),
        check_stripe(),
        return_exceptions=True
    )
    
    components = {
        "database": checks[0] if not isinstance(checks[0], Exception) 
                   else ComponentHealth(status=HealthStatus.UNHEALTHY, message=str(checks[0])),
        "redis": checks[1] if not isinstance(checks[1], Exception)
                else ComponentHealth(status=HealthStatus.UNHEALTHY, message=str(checks[1])),
        "stripe": checks[2] if not isinstance(checks[2], Exception)
                 else ComponentHealth(status=HealthStatus.DEGRADED, message=str(checks[2])),
    }
    
    # Determine overall status
    statuses = [c.status for c in components.values()]
    if HealthStatus.UNHEALTHY in statuses:
        overall = HealthStatus.UNHEALTHY
    elif HealthStatus.DEGRADED in statuses:
        overall = HealthStatus.DEGRADED
    else:
        overall = HealthStatus.HEALTHY
    
    response = HealthResponse(
        status=overall,
        components=components,
        version=settings.VERSION
    )
    
    # Return 503 if unhealthy (load balancer should stop routing)
    if overall == HealthStatus.UNHEALTHY:
        return JSONResponse(
            status_code=503,
            content=response.dict()
        )
    
    return response

# Kubernetes probes
@app.get("/health/live")
async def liveness():
    """Is the process running?"""
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness():
    """Can we serve traffic?"""
    db_health = await check_database()
    if db_health.status == HealthStatus.UNHEALTHY:
        raise HTTPException(503, "Database unavailable")
    return {"status": "ready"}
```

---

## Alerting Strategy

### What to Alert On

```python
# Alert: High error rate
# prometheus: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01

# Alert: High latency
# prometheus: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 2

# Alert: External API failures
EXTERNAL_API_ERRORS = Counter(
    "external_api_errors_total",
    "External API errors",
    ["service", "error_type"]
)

async def call_external_with_alerting(service: str, func, *args):
    try:
        return await func(*args)
    except TimeoutError:
        EXTERNAL_API_ERRORS.labels(service=service, error_type="timeout").inc()
        raise
    except HTTPStatusError as e:
        EXTERNAL_API_ERRORS.labels(service=service, error_type=f"http_{e.response.status_code}").inc()
        raise
    except Exception as e:
        EXTERNAL_API_ERRORS.labels(service=service, error_type="unknown").inc()
        raise
```

### Alert Tiers

```yaml
# alerting_rules.yml

# P1 - Page immediately (PagerDuty)
- alert: HighErrorRate
  expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "High error rate: {{ $value | humanizePercentage }}"

# P2 - Alert to Slack
- alert: ElevatedLatency
  expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 2
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "P95 latency above 2s: {{ $value | humanizeDuration }}"

# P3 - Log for review
- alert: HighDatabaseConnections
  expr: db_pool_connections{state="active"} / db_pool_connections{state="total"} > 0.8
  for: 10m
  labels:
    severity: info
```

---

## Mastery Checkpoints

### Conceptual Questions

1. **What's the difference between logging, metrics, and traces?**

   *Answer*: Logs are discrete events with details ("User 123 logged in at 10:30"). Metrics are aggregated measurements over time ("Average response time is 150ms, 1000 requests/minute"). Traces follow a single request across services ("Request abc123 went API→auth→database→cache→response"). All three are needed for full observability.

2. **Why use structured logging instead of string formatting?**

   *Answer*: Structured logs (JSON) are machine-parseable, enabling log aggregation tools (ELK, Datadog) to search, filter, and alert on specific fields. "user_id=123 AND error_code=PAYMENT_FAILED" is impossible with unstructured "User 123 had a payment failure."

3. **What is request ID and why is it important?**

   *Answer*: Request ID is a unique identifier propagated through all logs, metrics, and traces for a single request. When a user reports "something broke," you can find all related logs across services with one ID. Without it, correlating logs from different services is nearly impossible.

4. **Why would you return 503 on a health check failure?**

   *Answer*: Load balancers check health endpoints to decide where to route traffic. 503 tells the load balancer "don't send me traffic." This allows graceful handling of partial failures - if database is down, stop routing to this instance, but other healthy instances keep serving.

5. **What metrics would you alert on for a payment processing API?**

   *Answer*: (1) Payment failure rate > threshold, (2) Payment latency p95 > threshold, (3) Payment provider API errors, (4) Queue depth for async payments growing, (5) Mismatch between payments created vs confirmed. Alert on anomaly, not just threshold - sudden spike matters even if under threshold.

### Scenario Questions

6. **Your API is returning 500 errors sporadically. How do you debug it?**

   *Answer*:
   1. Check error rate metrics to understand scope and timing
   2. Find request IDs from affected requests (user reports, monitoring)
   3. Search logs by request ID to see full request context
   4. Look at distributed traces to see where the error occurred
   5. Check for common patterns: specific endpoint? specific user? specific time?
   6. Review recent deployments, config changes
   7. Check external service health if errors correlate

7. **Design logging for an order processing system that spans multiple services.**

   *Answer*:
   ```python
   # Generate at API gateway
   trace_id = str(uuid4())
   
   # Pass in all requests
   headers = {"X-Trace-ID": trace_id, "X-Request-ID": request_id}
   
   # Log with context at each service
   logger.info("Order received", extra={
       "trace_id": trace_id,
       "order_id": order.id,
       "service": "order-api"
   })
   
   # Payment service
   logger.info("Payment processing", extra={
       "trace_id": trace_id,  # Same trace!
       "order_id": order.id,
       "amount": amount,
       "service": "payment-service"
   })
   
   # Now you can search: trace_id=abc123 to see entire flow
   ```

8. **Your health check passes but users report slow responses. What's wrong and how do you fix the health check?**

   *Answer*: Health check only tests connectivity, not performance. Improve by:
   ```python
   @app.get("/health/ready")
   async def readiness():
       # Check database latency, not just connectivity
       db_latency = await measure_db_latency()
       if db_latency > 1.0:  # 1 second threshold
           raise HTTPException(503, f"Database slow: {db_latency}s")
       
       # Check dependency latencies
       redis_latency = await measure_redis_latency()
       if redis_latency > 0.1:
           raise HTTPException(503, f"Redis slow: {redis_latency}s")
       
       return {"status": "ready", "db_latency": db_latency}
   ```

9. **You need to add tracing to an existing application with minimal code changes. How?**

   *Answer*: Use auto-instrumentation:
   ```python
   from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
   from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
   from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
   
   # One-time setup
   FastAPIInstrumentor.instrument_app(app)  # All routes traced
   HTTPXClientInstrumentor().instrument()    # All HTTP calls traced
   SQLAlchemyInstrumentor().instrument()     # All DB queries traced
   
   # Add custom spans only where needed
   with tracer.start_as_current_span("critical_business_logic"):
       result = do_important_thing()
   ```

10. **How do you handle logging sensitive data (PII, passwords, credit cards)?**

    *Answer*:
    ```python
    import re
    
    class SensitiveDataFilter(logging.Filter):
        PATTERNS = [
            (r'\b\d{16}\b', '****CARD****'),  # Credit card
            (r'password["\']?\s*[:=]\s*["\']?[^"\']+', 'password=***'),
            (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.***'),
        ]
        
        def filter(self, record):
            if hasattr(record, 'msg'):
                for pattern, replacement in self.PATTERNS:
                    record.msg = re.sub(pattern, replacement, str(record.msg))
            return True
    
    # Or redact at the source
    def sanitize_for_logging(data: dict) -> dict:
        sensitive_keys = {'password', 'credit_card', 'ssn', 'api_key'}
        return {
            k: '***' if k in sensitive_keys else v
            for k, v in data.items()
        }
    
    logger.info("User update", extra=sanitize_for_logging(user_data))
    ```

---

## Interview Framing

When discussing observability:

1. **Show systematic thinking**: "I implement all three pillars - logs for debugging, metrics for alerting, traces for distributed requests. Each serves a different purpose and they complement each other."

2. **Emphasize production experience**: "Request IDs are non-negotiable. When a user reports an error, I can find that exact request across all services in seconds instead of searching through millions of logs."

3. **Discuss proactive monitoring**: "I don't wait for users to report problems. I alert on error rate increases, latency spikes, and queue depth growth. Often I know about issues before they impact users."

4. **Connect to business metrics**: "Technical metrics like latency matter, but I also track business metrics - orders per minute, payment failure rates, user signups. These tell me if the system is actually working for the business."

5. **Mention tooling pragmatically**: "I've used ELK, Datadog, and Prometheus/Grafana. The specific tool matters less than having proper instrumentation. I can switch tools if needed because my code is properly instrumented."
