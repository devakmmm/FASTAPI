# File: backend_fastapi_mastery/07_external_api_integration_patterns.md

# External API Integration Patterns

## Why This Matters

Your backend will call external APIs: payment processors, email services, third-party data providers, microservices. These integrations are where things go wrong:

- Networks fail
- Services go down
- Responses are slow
- Rate limits trigger
- Data formats change

The difference between a junior and senior engineer is how they handle these failure modes.

---

## The Naive Approach (Don't Do This)

```python
import httpx

@app.post("/charge")
async def charge_customer(request: ChargeRequest):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.stripe.com/v1/charges",
            json={"amount": request.amount, "customer": request.customer_id}
        )
        return response.json()
```

**Problems:**
- No timeout: Request hangs forever if Stripe is slow
- No retries: Transient network errors fail permanently
- No error handling: HTTP errors crash the endpoint
- No rate limiting: You might overwhelm the external API
- No idempotency: Retrying might double-charge
- New connection per request: Inefficient

---

## Robust HTTP Client Setup

### Client Configuration

```python
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create client with production-ready settings
    app.state.http_client = httpx.AsyncClient(
        # Timeouts
        timeout=httpx.Timeout(
            connect=5.0,      # Time to establish connection
            read=30.0,        # Time to read response
            write=10.0,       # Time to send request
            pool=10.0         # Time to get connection from pool
        ),
        # Connection limits
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0
        ),
        # Follow redirects
        follow_redirects=True,
        # Default headers
        headers={
            "User-Agent": "MyApp/1.0",
            "Accept": "application/json"
        }
    )
    
    yield
    
    await app.state.http_client.aclose()

app = FastAPI(lifespan=lifespan)
```

### Per-Service Clients

```python
class StripeClient:
    def __init__(self, api_key: str, http_client: httpx.AsyncClient):
        self.api_key = api_key
        self.client = http_client
        self.base_url = "https://api.stripe.com/v1"
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            **kwargs.pop("headers", {})
        }
        
        response = await self.client.request(
            method,
            f"{self.base_url}{endpoint}",
            headers=headers,
            **kwargs
        )
        response.raise_for_status()
        return response.json()
    
    async def create_charge(self, amount: int, customer_id: str) -> dict:
        return await self._request(
            "POST",
            "/charges",
            data={"amount": amount, "customer": customer_id}
        )
```

---

## Retry Strategies

### Why Retries?

Transient failures are common:
- Network hiccups
- DNS resolution delays
- Load balancer rebalancing
- Service restarts

A quick retry often succeeds when the first attempt failed.

### Basic Retry with Tenacity

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
import httpx

class TransientError(Exception):
    """Error that might succeed on retry"""
    pass

def is_retryable_error(exception: Exception) -> bool:
    """Determine if error warrants retry"""
    if isinstance(exception, httpx.TimeoutException):
        return True
    if isinstance(exception, httpx.HTTPStatusError):
        # Retry on server errors and rate limits
        return exception.response.status_code in [429, 500, 502, 503, 504]
    return False

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((TransientError, httpx.TimeoutException))
)
async def fetch_with_retry(client: httpx.AsyncClient, url: str) -> dict:
    response = await client.get(url)
    
    if response.status_code in [429, 500, 502, 503, 504]:
        raise TransientError(f"Got {response.status_code}, retrying...")
    
    response.raise_for_status()
    return response.json()
```

### Exponential Backoff Explained

```
Attempt 1: Immediate
  ↓ Wait 1 second
Attempt 2: 
  ↓ Wait 2 seconds
Attempt 3:
  ↓ Wait 4 seconds
Attempt 4:
  ↓ ... (exponentially increasing)
```

This prevents thundering herd: if a service recovers, it isn't immediately overwhelmed by retries.

### Jitter

Add randomness to prevent synchronized retries:

```python
from tenacity import wait_exponential_jitter

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=1, max=60)  # Adds random jitter
)
async def fetch_with_jitter(url: str):
    ...
```

### Production Retry Pattern

```python
from tenacity import (
    AsyncRetrying,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception,
    before_sleep_log
)
import logging

logger = logging.getLogger(__name__)

class ExternalAPIClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
    
    async def call_api(self, url: str, method: str = "GET", **kwargs) -> dict:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=1, max=10),
            retry=retry_if_exception(self._is_retryable),
            before_sleep=before_sleep_log(logger, logging.WARNING)
        ):
            with attempt:
                response = await self.client.request(method, url, **kwargs)
                
                # Raise for retry on retryable status codes
                if response.status_code in [429, 500, 502, 503, 504]:
                    raise RetryableError(
                        f"Status {response.status_code}",
                        response=response
                    )
                
                response.raise_for_status()
                return response.json()
    
    @staticmethod
    def _is_retryable(exception: Exception) -> bool:
        if isinstance(exception, httpx.TimeoutException):
            return True
        if isinstance(exception, RetryableError):
            return True
        if isinstance(exception, httpx.ConnectError):
            return True
        return False
```

---

## Circuit Breaker Pattern

### The Problem

If an external service is down, every request:
1. Waits for timeout
2. Retries multiple times
3. Finally fails

Your users wait 30+ seconds for inevitable failure.

### Circuit Breaker Solution

```
┌─────────────────────────────────────────────────────────────┐
│                    Circuit Breaker States                    │
│                                                             │
│   CLOSED ──(failures > threshold)──► OPEN                  │
│     │                                  │                    │
│     │                          (timeout expires)           │
│     │                                  │                    │
│     │◄──(success)──────────────── HALF-OPEN               │
│     │                                  │                    │
│     │◄──────────(failure)─────────────┘                    │
│                                                             │
│   CLOSED: Normal operation, requests pass through          │
│   OPEN: Fail fast, don't call service                      │
│   HALF-OPEN: Test if service recovered                     │
└─────────────────────────────────────────────────────────────┘
```

### Implementation

```python
import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Any
import logging

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.half_open_calls = 0
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit breaker: OPEN -> HALF_OPEN")
            else:
                raise CircuitOpenError("Circuit breaker is OPEN")
        
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_max_calls:
                raise CircuitOpenError("Circuit breaker is HALF_OPEN, max calls reached")
            self.half_open_calls += 1
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        if self.last_failure_time is None:
            return True
        return datetime.now() > self.last_failure_time + timedelta(seconds=self.recovery_timeout)
    
    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            logger.info("Circuit breaker: HALF_OPEN -> CLOSED")
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0
    
    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker: HALF_OPEN -> OPEN")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker: CLOSED -> OPEN (failures: {self.failure_count})")

class CircuitOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass

# Usage
stripe_circuit = CircuitBreaker(failure_threshold=5, recovery_timeout=30)

async def create_charge(amount: int, customer_id: str):
    return await stripe_circuit.call(
        stripe_client.create_charge,
        amount,
        customer_id
    )
```

### Using with Fallback

```python
async def get_product_recommendations(user_id: int) -> list:
    try:
        return await ml_circuit.call(
            ml_service.get_recommendations,
            user_id
        )
    except CircuitOpenError:
        logger.warning("ML service circuit open, using fallback")
        return get_popular_products()  # Fallback to static recommendations
    except Exception as e:
        logger.error(f"ML service error: {e}")
        return get_popular_products()
```

---

## Timeout Configuration

### Layered Timeouts

```python
# Layer 1: HTTP client timeout
client = httpx.AsyncClient(timeout=30.0)

# Layer 2: Per-request timeout
response = await client.get(url, timeout=10.0)

# Layer 3: Application-level timeout
try:
    result = await asyncio.wait_for(
        complex_api_operation(),
        timeout=60.0
    )
except asyncio.TimeoutError:
    # Handle timeout
```

### Timeout Strategy

```python
class APITimeouts:
    """Centralized timeout configuration"""
    
    # Fast operations (health checks, simple reads)
    FAST = httpx.Timeout(connect=2.0, read=5.0, write=2.0, pool=5.0)
    
    # Normal operations
    NORMAL = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
    
    # Slow operations (file uploads, batch processing)
    SLOW = httpx.Timeout(connect=10.0, read=120.0, write=60.0, pool=30.0)

# Usage
await client.get("/health", timeout=APITimeouts.FAST)
await client.post("/data", json=data, timeout=APITimeouts.NORMAL)
await client.post("/upload", files=files, timeout=APITimeouts.SLOW)
```

---

## Idempotency Keys

### The Problem

```
Client                         Server                         Stripe
  │                              │                              │
  ├────── POST /charge ──────────►                              │
  │                              ├──── Create charge ───────────►
  │                              │                              │
  │       ◄─── 504 Timeout ──────┤  (charge created, response lost)
  │                              │                              │
  ├────── POST /charge ──────────►                              │
  │       (retry)                ├──── Create charge ───────────►
  │                              │                              │
  │       ◄─── 200 OK ───────────┤  (DOUBLE CHARGE!)           │
```

### The Solution: Idempotency Keys

```python
import uuid

async def create_charge_idempotent(
    client: httpx.AsyncClient,
    amount: int,
    customer_id: str,
    idempotency_key: str | None = None
) -> dict:
    """
    Creates a charge with idempotency.
    Same idempotency_key = same result, no double charge.
    """
    key = idempotency_key or str(uuid.uuid4())
    
    response = await client.post(
        "https://api.stripe.com/v1/charges",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Idempotency-Key": key  # Stripe returns cached result for same key
        },
        data={
            "amount": amount,
            "customer": customer_id
        }
    )
    
    return response.json()
```

### Client-Side Idempotency Key Strategy

```python
from hashlib import sha256

def generate_idempotency_key(
    user_id: int,
    operation: str,
    amount: int,
    timestamp_bucket: int
) -> str:
    """
    Generate deterministic idempotency key.
    Same inputs = same key = no duplicate operations.
    """
    # Bucket timestamp to 5-minute windows
    bucket = timestamp_bucket // 300
    
    data = f"{user_id}:{operation}:{amount}:{bucket}"
    return sha256(data.encode()).hexdigest()

# Usage
key = generate_idempotency_key(
    user_id=123,
    operation="charge",
    amount=1000,
    timestamp_bucket=int(time.time())
)
```

### Server-Side Idempotency

```python
from fastapi import Header
import redis.asyncio as redis

class IdempotencyManager:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.ttl = 86400  # 24 hours
    
    async def get_cached_response(self, key: str) -> dict | None:
        cached = await self.redis.get(f"idempotency:{key}")
        if cached:
            return json.loads(cached)
        return None
    
    async def cache_response(self, key: str, response: dict):
        await self.redis.set(
            f"idempotency:{key}",
            json.dumps(response),
            ex=self.ttl
        )
    
    async def mark_in_progress(self, key: str) -> bool:
        """Returns True if we acquired the lock"""
        return await self.redis.set(
            f"idempotency:lock:{key}",
            "1",
            ex=60,  # 1 minute lock
            nx=True  # Only set if not exists
        )

@app.post("/charges")
async def create_charge(
    request: ChargeRequest,
    idempotency_key: str = Header(...),
    idempotency: IdempotencyManager = Depends(get_idempotency_manager)
):
    # Check for cached response
    cached = await idempotency.get_cached_response(idempotency_key)
    if cached:
        return cached
    
    # Acquire lock to prevent concurrent duplicate processing
    if not await idempotency.mark_in_progress(idempotency_key):
        raise HTTPException(409, "Request already in progress")
    
    try:
        # Process the charge
        result = await stripe_client.create_charge(
            amount=request.amount,
            customer_id=request.customer_id,
            idempotency_key=idempotency_key
        )
        
        # Cache the response
        await idempotency.cache_response(idempotency_key, result)
        
        return result
    finally:
        # Release lock
        await idempotency.redis.delete(f"idempotency:lock:{idempotency_key}")
```

---

## Failure Isolation

### Bulkhead Pattern

Don't let one failing service affect others:

```python
import asyncio

class BulkheadManager:
    """Limit concurrent calls to each service"""
    
    def __init__(self):
        self.semaphores = {}
    
    def get_semaphore(self, service: str, limit: int = 10) -> asyncio.Semaphore:
        if service not in self.semaphores:
            self.semaphores[service] = asyncio.Semaphore(limit)
        return self.semaphores[service]

bulkhead = BulkheadManager()

async def call_payment_service(data: dict):
    async with bulkhead.get_semaphore("payment", limit=20):
        return await payment_client.process(data)

async def call_notification_service(data: dict):
    async with bulkhead.get_semaphore("notification", limit=50):
        return await notification_client.send(data)

# Even if payment service is slow (filling up its 20 slots),
# notification service still has its own 50 slots available
```

### Graceful Degradation

```python
@app.get("/product/{product_id}")
async def get_product(product_id: int):
    # Critical: Must succeed
    product = await db.get_product(product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    
    # Non-critical: Okay to fail
    reviews = await safe_fetch(
        review_service.get_reviews(product_id),
        default=[],
        timeout=5.0
    )
    
    recommendations = await safe_fetch(
        ml_service.get_recommendations(product_id),
        default=await db.get_popular_products(),  # Fallback
        timeout=3.0
    )
    
    return {
        "product": product,
        "reviews": reviews,
        "recommendations": recommendations
    }

async def safe_fetch(coro, default, timeout: float):
    """Fetch with timeout and fallback"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching {coro}")
        return default
    except Exception as e:
        logger.error(f"Error fetching {coro}: {e}")
        return default
```

---

## Rate Limiting

### Respecting External Rate Limits

```python
from asyncio import Semaphore, sleep
from time import time

class RateLimiter:
    """Token bucket rate limiter"""
    
    def __init__(self, rate: float, capacity: int):
        """
        rate: tokens per second
        capacity: max tokens (burst size)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time()
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        async with self.lock:
            now = time()
            elapsed = now - self.last_update
            self.last_update = now
            
            # Add tokens based on elapsed time
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            
            if self.tokens < 1:
                # Wait for token
                wait_time = (1 - self.tokens) / self.rate
                await sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1

# 100 requests per second, burst of 10
stripe_rate_limiter = RateLimiter(rate=100, capacity=10)

async def call_stripe_api(endpoint: str, data: dict):
    await stripe_rate_limiter.acquire()
    return await stripe_client.request(endpoint, data)
```

### Handling 429 Responses

```python
async def call_with_rate_limit_handling(
    client: httpx.AsyncClient,
    url: str,
    **kwargs
) -> dict:
    max_retries = 3
    
    for attempt in range(max_retries):
        response = await client.request("GET", url, **kwargs)
        
        if response.status_code == 429:
            # Get retry-after from header or use exponential backoff
            retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
            logger.warning(f"Rate limited, waiting {retry_after}s")
            await asyncio.sleep(retry_after)
            continue
        
        response.raise_for_status()
        return response.json()
    
    raise RateLimitExceeded("Max retries exceeded for rate limit")
```

---

## Complete API Client Pattern

```python
import httpx
import asyncio
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential_jitter
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class PaymentServiceClient:
    """Production-ready external API client"""
    
    def __init__(
        self,
        base_url: str,
        api_key: str,
        http_client: httpx.AsyncClient,
        circuit_breaker: CircuitBreaker,
        rate_limiter: RateLimiter
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.client = http_client
        self.circuit = circuit_breaker
        self.rate_limiter = rate_limiter
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> dict:
        """Make request with all resilience patterns"""
        
        # Apply rate limiting
        await self.rate_limiter.acquire()
        
        # Build headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **kwargs.pop("headers", {})
        }
        
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        
        url = f"{self.base_url}{endpoint}"
        
        # Wrap in circuit breaker
        async def make_request():
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential_jitter(initial=1, max=10),
                retry=self._should_retry
            ):
                with attempt:
                    response = await self.client.request(
                        method,
                        url,
                        headers=headers,
                        **kwargs
                    )
                    
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 5))
                        await asyncio.sleep(retry_after)
                        raise RateLimitError("Rate limited")
                    
                    if response.status_code >= 500:
                        raise ServerError(f"Server error: {response.status_code}")
                    
                    response.raise_for_status()
                    return response.json()
        
        return await self.circuit.call(make_request)
    
    @staticmethod
    def _should_retry(exception: Exception) -> bool:
        if isinstance(exception, (RateLimitError, ServerError)):
            return True
        if isinstance(exception, httpx.TimeoutException):
            return True
        if isinstance(exception, httpx.ConnectError):
            return True
        return False
    
    # Business methods
    async def create_charge(
        self,
        amount: int,
        customer_id: str,
        idempotency_key: str
    ) -> dict:
        return await self._request(
            "POST",
            "/charges",
            idempotency_key=idempotency_key,
            json={
                "amount": amount,
                "customer": customer_id
            }
        )
    
    async def get_customer(self, customer_id: str) -> dict:
        return await self._request(
            "GET",
            f"/customers/{customer_id}"
        )
    
    async def refund_charge(
        self,
        charge_id: str,
        amount: Optional[int] = None,
        idempotency_key: str = None
    ) -> dict:
        data = {"charge": charge_id}
        if amount:
            data["amount"] = amount
        
        return await self._request(
            "POST",
            "/refunds",
            idempotency_key=idempotency_key,
            json=data
        )
```

---

## Mastery Checkpoints

### Conceptual Questions

1. **Why use exponential backoff instead of fixed delays for retries?**

   *Answer*: Fixed delays cause synchronized retries - if 1000 clients all retry after exactly 1 second, the recovering service gets 1000 requests at once. Exponential backoff with jitter spreads retries over time, giving the service breathing room to recover. Each retry waits longer, reducing load on struggling services.

2. **When should a circuit breaker be OPEN vs let requests through?**

   *Answer*: OPEN when failures exceed threshold, indicating the service is down. Letting requests through would cause timeouts and slow down your API. OPEN state fails fast with a clear error, then periodically tests (HALF-OPEN) to see if service recovered.

3. **Why do we need idempotency keys for payment operations?**

   *Answer*: Network failures can cause requests to succeed on the server but timeout for the client. Without idempotency keys, retrying would create duplicate charges. With them, the server recognizes "I already processed this request" and returns the cached result instead of processing again.

4. **What's the difference between client-side and server-side rate limiting?**

   *Answer*: Client-side rate limiting proactively limits your request rate to avoid hitting server limits. Server-side (429 responses) tells you you've exceeded limits. Client-side is more efficient - you don't waste requests that will be rejected. Use both: client-side to stay under limits, server-side handling for unexpected bursts.

5. **How does the bulkhead pattern prevent cascading failures?**

   *Answer*: It isolates resources per service. If payment service is slow and consumes all your connection pool, other services (notifications, analytics) still have their own pools. Without bulkheads, one slow service exhausts shared resources and everything fails.

### Scenario Questions

6. **You're integrating with an API that has a rate limit of 1000 requests/minute. Your traffic spikes to 5000 requests/minute during peak. How do you handle this?**

   *Answer*:
   ```python
   # 1. Queue excess requests
   class RateLimitedQueue:
       def __init__(self, rate_per_minute: int):
           self.semaphore = asyncio.Semaphore(rate_per_minute // 60)  # Per second
           self.queue = asyncio.Queue()
       
       async def enqueue(self, request):
           await self.queue.put(request)
       
       async def process_loop(self):
           while True:
               request = await self.queue.get()
               async with self.semaphore:
                   await process_request(request)
               await asyncio.sleep(1/16.67)  # 1000/60 per second
   
   # 2. Graceful degradation for non-critical requests
   # 3. Cache responses to reduce API calls
   # 4. Consider batch endpoints if API offers them
   ```

7. **Your payment provider is experiencing intermittent failures (~10% of requests fail). How do you maintain reliability?**

   *Answer*:
   ```python
   async def create_charge_resilient(amount: int, customer_id: str):
       idempotency_key = generate_key(customer_id, amount)
       
       for attempt in range(3):
           try:
               result = await payment_client.create_charge(
                   amount=amount,
                   customer_id=customer_id,
                   idempotency_key=idempotency_key
               )
               return result
           except TransientError:
               if attempt < 2:
                   await asyncio.sleep(2 ** attempt)  # Backoff
                   continue
               raise
       
       # After retries exhausted:
       # 1. Queue for background retry
       await retry_queue.enqueue({
           "operation": "charge",
           "data": {"amount": amount, "customer_id": customer_id},
           "idempotency_key": idempotency_key
       })
       # 2. Return pending status to user
       return {"status": "pending", "message": "Processing..."}
   ```

8. **You need to call 5 external services to assemble a response. Service A is critical, others are nice-to-have. How do you structure this?**

   *Answer*:
   ```python
   @app.get("/dashboard")
   async def get_dashboard(user_id: int):
       # Critical: Must succeed
       user_data = await user_service.get_user(user_id)  # No fallback
       
       # Nice-to-have: Run concurrently with timeouts
       non_critical = await asyncio.gather(
           safe_call(notification_service.get_count(user_id), default=0, timeout=2),
           safe_call(analytics_service.get_stats(user_id), default={}, timeout=3),
           safe_call(ml_service.get_recommendations(user_id), default=[], timeout=2),
           safe_call(weather_service.get_local(user_id), default=None, timeout=1),
       )
       
       notifications, stats, recommendations, weather = non_critical
       
       return {
           "user": user_data,
           "notifications_count": notifications,
           "stats": stats,
           "recommendations": recommendations,
           "weather": weather
       }
   ```

9. **The external API you depend on changes their response format without notice. How do you protect against this?**

   *Answer*:
   ```python
   from pydantic import BaseModel, ValidationError
   
   class ExpectedResponse(BaseModel):
       id: str
       status: str
       amount: int
   
   async def call_api_safely(data: dict) -> ExpectedResponse:
       response = await client.post("/endpoint", json=data)
       raw = response.json()
       
       try:
           validated = ExpectedResponse.model_validate(raw)
           return validated
       except ValidationError as e:
           # Log the unexpected response for debugging
           logger.error(f"Unexpected API response format: {raw}")
           logger.error(f"Validation error: {e}")
           
           # Alert on-call
           await alert_service.send("External API response format changed!")
           
           # Attempt graceful handling or raise
           raise ExternalAPIContractViolation("API response format changed")
   
   # Also: Contract tests that run regularly to catch changes early
   ```

10. **You're building a checkout flow that calls inventory, payment, and shipping services. If payment succeeds but shipping fails, what do you do?**

    *Answer*:
    ```python
    async def checkout(order: Order):
        # Phase 1: Reserve resources
        inventory_reservation = await inventory_service.reserve(order.items)
        
        try:
            # Phase 2: Charge payment
            payment = await payment_service.charge(
                amount=order.total,
                idempotency_key=f"order_{order.id}"
            )
            
            try:
                # Phase 3: Create shipment
                shipment = await shipping_service.create(order)
                
            except ShippingError:
                # Compensate: Refund payment
                await payment_service.refund(
                    payment_id=payment.id,
                    idempotency_key=f"refund_{order.id}"
                )
                # Compensate: Release inventory
                await inventory_service.release(inventory_reservation.id)
                
                # Don't fail silently - alert and queue for manual review
                await alert_service.send(f"Checkout failed at shipping: {order.id}")
                raise CheckoutError("Shipping unavailable, payment refunded")
                
        except PaymentError:
            # Compensate: Release inventory
            await inventory_service.release(inventory_reservation.id)
            raise CheckoutError("Payment failed")
    ```

---

## Interview Framing

When discussing external API integration:

1. **Show failure awareness**: "I assume every external call can fail. I design for timeouts, retries, and graceful degradation. The question isn't if the service will be down, but when."

2. **Explain idempotency**: "For any operation that changes state, I use idempotency keys. This lets me safely retry without duplicating side effects. It's essential for payment processing."

3. **Discuss circuit breakers**: "I implement circuit breakers for all external dependencies. If a service is failing, I fail fast instead of making users wait for timeouts. I track failure rates and alert when circuits open."

4. **Connect to user experience**: "When the ML recommendation service is slow, I don't make users wait. I return product data immediately with a fallback recommendation, then potentially update async."

5. **Mention observability**: "I log every external call with latency, status code, and correlation ID. I can trace a user's request across all services. I alert on increased latency or error rates before users complain."
