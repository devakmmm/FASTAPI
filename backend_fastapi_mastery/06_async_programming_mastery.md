# File: backend_fastapi_mastery/06_async_programming_mastery.md

# Async Programming Mastery

## Why Async Matters for Backend Engineering

Modern backend systems spend most of their time **waiting**:
- Waiting for database queries
- Waiting for HTTP responses from external APIs
- Waiting for file I/O
- Waiting for cache responses

Synchronous code blocks during these waits. Async code does useful work while waiting.

```
Synchronous Server (4 workers):
Request 1: [████ DB Wait ████][Process]
Request 2:                            [████ DB Wait ████][Process]
Request 3:                                                        [████...
Request 5: ← Queued, waiting for worker

Async Server (1 worker):
Request 1: [██ DB ██]          [Process]
Request 2:   [██ DB ██]        [Process]
Request 3:     [██ DB ██]      [Process]
Request 4:       [██ DB ██]    [Process]
Request 5:         [██ DB ██]  [Process]
           ↑
           While Request 1 waits for DB,
           we start Requests 2, 3, 4, 5
```

---

## The Event Loop: Core Concept

### What Is the Event Loop?

The event loop is a single thread that:
1. Runs your code until it hits an `await`
2. When code awaits, switches to run other code
3. When awaited operation completes, resumes original code

```python
import asyncio

async def fetch_user(user_id: int):
    print(f"Starting fetch for user {user_id}")
    
    # await yields control to event loop
    await asyncio.sleep(1)  # Simulates database query
    
    print(f"Completed fetch for user {user_id}")
    return {"id": user_id, "name": f"User {user_id}"}

async def main():
    # These run concurrently, not sequentially
    results = await asyncio.gather(
        fetch_user(1),
        fetch_user(2),
        fetch_user(3),
    )
    print(f"Got {len(results)} users")

asyncio.run(main())
```

Output:
```
Starting fetch for user 1
Starting fetch for user 2
Starting fetch for user 3
Completed fetch for user 1
Completed fetch for user 2
Completed fetch for user 3
Got 3 users
```

Total time: ~1 second (not 3 seconds).

### How await Works

```python
async def example():
    # Code runs normally
    x = 1 + 1
    
    # await pauses this function, event loop runs other tasks
    result = await some_async_operation()
    # ↑ Event loop switches away here
    # ↓ Event loop returns here when operation completes
    
    # Resume with result
    return result
```

**Critical insight**: `await` is a **yield point**. It's where the event loop can switch tasks. Code between awaits runs without interruption.

---

## Async vs Sync in FastAPI

### FastAPI's Dual Support

FastAPI handles both async and sync functions:

```python
# Async: Runs directly on event loop
@app.get("/async")
async def async_endpoint():
    await asyncio.sleep(0.1)
    return {"type": "async"}

# Sync: Runs in thread pool
@app.get("/sync")
def sync_endpoint():
    time.sleep(0.1)
    return {"type": "sync"}
```

### When to Use Which

**Use `async def` when:**
- Calling async libraries (httpx, asyncpg, aioredis)
- All I/O operations have async versions
- You want maximum concurrency

**Use `def` when:**
- Using synchronous libraries (requests, psycopg2)
- Doing CPU-bound work
- Interfacing with legacy code

### The Fatal Mistake: Blocking in Async

```python
import time
import requests

# WRONG: Blocks the entire event loop!
@app.get("/broken")
async def broken_endpoint():
    # time.sleep is synchronous - BLOCKS everything
    time.sleep(1)
    
    # requests is synchronous - BLOCKS everything
    response = requests.get("https://api.example.com")
    
    return response.json()

# While this runs, NO other requests can be processed!
```

**The fix:**

```python
import asyncio
import httpx

# RIGHT: Use async operations
@app.get("/correct")
async def correct_endpoint():
    # asyncio.sleep is async - other tasks run during wait
    await asyncio.sleep(1)
    
    # httpx is async - other tasks run during wait
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com")
    
    return response.json()
```

**Or use sync function (runs in thread pool):**

```python
import time
import requests

# ALSO RIGHT: Sync function runs in thread pool
@app.get("/sync-correct")
def sync_correct_endpoint():
    time.sleep(1)  # Blocks this thread, not the event loop
    response = requests.get("https://api.example.com")
    return response.json()
```

---

## Concurrency Patterns

### asyncio.gather: Run Tasks Concurrently

```python
async def fetch_data_from_multiple_sources():
    async with httpx.AsyncClient() as client:
        # All three requests start immediately, run concurrently
        results = await asyncio.gather(
            client.get("https://api1.example.com/data"),
            client.get("https://api2.example.com/data"),
            client.get("https://api3.example.com/data"),
        )
    
    return [r.json() for r in results]

# Time: ~max(api1_time, api2_time, api3_time)
# Not: api1_time + api2_time + api3_time
```

### Handling Failures in gather

```python
# Default: One failure fails everything
results = await asyncio.gather(
    maybe_fails_1(),
    maybe_fails_2(),
)
# If either raises, gather raises

# With return_exceptions: Failures returned as exceptions
results = await asyncio.gather(
    maybe_fails_1(),
    maybe_fails_2(),
    return_exceptions=True
)
# results = [result1, Exception(...)]

# Process results
for result in results:
    if isinstance(result, Exception):
        logger.error(f"Task failed: {result}")
    else:
        process(result)
```

### asyncio.create_task: Fire and Forget

```python
async def send_analytics(event: dict):
    """Non-critical operation, don't wait for it"""
    async with httpx.AsyncClient() as client:
        await client.post("https://analytics.example.com", json=event)

@app.post("/orders")
async def create_order(order: OrderCreate):
    # Create the order (critical path)
    result = await order_service.create(order)
    
    # Fire off analytics (don't wait)
    asyncio.create_task(send_analytics({"event": "order_created", "order_id": result.id}))
    
    return result  # Returns immediately, analytics runs in background
```

**Caution**: Untracked tasks can be garbage collected. For important background work, use proper task management.

### Semaphores: Limit Concurrency

```python
# Problem: Calling 1000 URLs simultaneously overwhelms target
urls = [f"https://api.example.com/item/{i}" for i in range(1000)]

# Solution: Semaphore limits concurrent operations
semaphore = asyncio.Semaphore(10)  # Max 10 concurrent

async def fetch_with_limit(client: httpx.AsyncClient, url: str):
    async with semaphore:  # Wait for semaphore slot
        return await client.get(url)

async def fetch_all():
    async with httpx.AsyncClient() as client:
        tasks = [fetch_with_limit(client, url) for url in urls]
        return await asyncio.gather(*tasks)
```

### asyncio.wait_for: Timeouts

```python
async def risky_operation():
    await asyncio.sleep(10)  # Takes too long

async def with_timeout():
    try:
        result = await asyncio.wait_for(
            risky_operation(),
            timeout=5.0
        )
    except asyncio.TimeoutError:
        # Operation took too long
        return {"error": "Operation timed out"}
    
    return result
```

### asyncio.shield: Protect from Cancellation

```python
async def critical_database_operation():
    """Must complete once started, can't be interrupted"""
    await db.begin_transaction()
    await db.execute("UPDATE accounts SET balance = balance - 100")
    await db.execute("UPDATE accounts SET balance = balance + 100")
    await db.commit()

async def process_transfer():
    try:
        # Shield prevents cancellation from interrupting this
        await asyncio.shield(critical_database_operation())
    except asyncio.CancelledError:
        # We got cancelled, but the database operation completed
        pass
```

---

## httpx vs requests

### requests: Synchronous HTTP

```python
import requests

# BLOCKS until response received
response = requests.get("https://api.example.com")

# In async context, this blocks the event loop!
```

### httpx: Async HTTP

```python
import httpx

# Async client for async code
async with httpx.AsyncClient() as client:
    response = await client.get("https://api.example.com")

# httpx also has sync interface
response = httpx.get("https://api.example.com")
```

### httpx Best Practices

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

# Reuse client across requests (connection pooling)
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(
        timeout=30.0,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
    )
    yield
    await app.state.http_client.aclose()

app = FastAPI(lifespan=lifespan)

def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client

@app.get("/external")
async def call_external(client: httpx.AsyncClient = Depends(get_http_client)):
    response = await client.get("https://api.example.com")
    return response.json()
```

### Timeout Configuration

```python
# Per-request timeouts
client = httpx.AsyncClient(
    timeout=httpx.Timeout(
        connect=5.0,    # Time to establish connection
        read=30.0,      # Time to receive response
        write=10.0,     # Time to send request
        pool=10.0       # Time to get connection from pool
    )
)

# Override for specific request
response = await client.get(
    "https://slow-api.example.com",
    timeout=60.0
)
```

---

## Thread Pool vs asyncio

### When to Use Threads

For blocking operations that don't have async versions:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Create thread pool
thread_pool = ThreadPoolExecutor(max_workers=10)

def blocking_operation(data):
    """Legacy code that can't be made async"""
    import some_blocking_library
    return some_blocking_library.process(data)

async def async_wrapper(data):
    """Run blocking code in thread pool"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(thread_pool, blocking_operation, data)
    return result
```

### FastAPI's Automatic Thread Pool

FastAPI runs sync functions in a thread pool automatically:

```python
# FastAPI handles this correctly
@app.get("/sync")
def sync_endpoint():
    # This runs in a thread pool, not blocking event loop
    time.sleep(1)
    return {"status": "ok"}
```

### CPU-Bound Work

For CPU-intensive operations, use `ProcessPoolExecutor`:

```python
from concurrent.futures import ProcessPoolExecutor
import asyncio

process_pool = ProcessPoolExecutor(max_workers=4)

def cpu_intensive_calculation(data):
    """Heavy computation"""
    result = 0
    for i in range(10_000_000):
        result += i * data
    return result

async def process_data(data):
    loop = asyncio.get_event_loop()
    # Run in separate process to avoid blocking
    result = await loop.run_in_executor(process_pool, cpu_intensive_calculation, data)
    return result
```

---

## Performance Implications

### Measuring Async Performance

```python
import asyncio
import time

async def measure_concurrent():
    """Measure concurrent async operations"""
    start = time.time()
    
    # 10 operations, each takes 1 second
    await asyncio.gather(*[asyncio.sleep(1) for _ in range(10)])
    
    elapsed = time.time() - start
    print(f"Concurrent: {elapsed:.2f}s")  # ~1 second

def measure_sequential():
    """Measure sequential sync operations"""
    start = time.time()
    
    # 10 operations, each takes 1 second
    for _ in range(10):
        time.sleep(1)
    
    elapsed = time.time() - start
    print(f"Sequential: {elapsed:.2f}s")  # ~10 seconds
```

### Real-World Impact

```python
# E-commerce endpoint that fetches multiple data sources

# SLOW: Sequential fetching
@app.get("/product/{product_id}")
async def get_product_slow(product_id: int):
    product = await db.get_product(product_id)        # 50ms
    reviews = await db.get_reviews(product_id)         # 100ms
    recommendations = await ml_service.get_recs(product_id)  # 200ms
    inventory = await inventory_service.check(product_id)    # 50ms
    
    return {...}
    # Total: 400ms (sequential)

# FAST: Concurrent fetching
@app.get("/product/{product_id}")
async def get_product_fast(product_id: int):
    product, reviews, recommendations, inventory = await asyncio.gather(
        db.get_product(product_id),          # 50ms  ─┐
        db.get_reviews(product_id),          # 100ms  │ Run
        ml_service.get_recs(product_id),     # 200ms  │ concurrently
        inventory_service.check(product_id), # 50ms  ─┘
    )
    
    return {...}
    # Total: 200ms (concurrent, limited by slowest)
```

### When Async Doesn't Help

Async doesn't help with:
- CPU-bound operations
- Operations that must be sequential
- Single operations (no concurrency opportunity)

```python
# Async doesn't help here
@app.get("/compute")
async def compute_something():
    # This is CPU-bound, not I/O-bound
    # Async adds overhead without benefit
    result = expensive_calculation()  # CPU work, no awaits
    return result

# Better as sync (avoids async overhead)
@app.get("/compute")
def compute_something():
    result = expensive_calculation()
    return result
```

---

## Latency Reasoning

### Understanding Latency Sources

```
Client Request
    │
    ├── Network to server (~10-100ms)
    │
    ▼
Server Processing
    │
    ├── Parse request (~0.1ms)
    ├── Authentication (~1-10ms, may involve DB/cache)
    ├── Database query (~1-50ms per query)
    ├── External API call (~50-500ms)
    ├── Business logic (~0.1-1ms)
    └── Serialize response (~0.1ms)
    │
    ▼
    │
    └── Network to client (~10-100ms)
```

### Optimizing for Latency

```python
@app.get("/dashboard")
async def get_dashboard(user_id: int):
    # Identify dependencies
    # user_data: no deps
    # orders: needs user_data? No, just user_id
    # notifications: needs user_data? No, just user_id
    # analytics: needs orders? Yes
    
    # Run independent calls concurrently
    user_data, orders, notifications = await asyncio.gather(
        get_user(user_id),
        get_orders(user_id),
        get_notifications(user_id),
    )
    
    # Then run dependent calls
    analytics = await compute_analytics(orders)
    
    return {
        "user": user_data,
        "orders": orders,
        "notifications": notifications,
        "analytics": analytics,
    }
```

### Latency vs Throughput

- **Latency**: Time for single request
- **Throughput**: Requests per second

Async improves **throughput** dramatically but may not improve single-request **latency**.

```python
# This endpoint has same latency async or sync: ~100ms
@app.get("/simple")
async def simple_endpoint():
    result = await db.query("SELECT * FROM users WHERE id = 1")  # 100ms
    return result

# But async handles more concurrent requests
# Sync: 1 request at a time per worker
# Async: Hundreds of requests concurrently
```

---

## Debugging Async Code

### Finding Blocking Calls

```python
import asyncio

# Enable debug mode to detect blocking calls
asyncio.get_event_loop().set_debug(True)

# Or via environment variable
# PYTHONASYNCIODEBUG=1 python main.py
```

### Common Async Bugs

**1. Forgetting await:**
```python
# WRONG: Returns coroutine object, not result
async def get_user():
    return await db.get_user(1)

@app.get("/user")
async def endpoint():
    user = get_user()  # Missing await!
    # user is a coroutine, not the result
    return user  # Returns coroutine object

# RIGHT
@app.get("/user")
async def endpoint():
    user = await get_user()
    return user
```

**2. Creating tasks that never run:**
```python
# WRONG: Task created but never awaited
async def endpoint():
    task = asyncio.create_task(background_work())
    return {"status": "ok"}
    # task may be garbage collected before running!

# RIGHT: Track tasks properly
background_tasks: set[asyncio.Task] = set()

async def endpoint():
    task = asyncio.create_task(background_work())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return {"status": "ok"}
```

**3. Sharing mutable state without locks:**
```python
# WRONG: Race condition
counter = 0

async def increment():
    global counter
    value = counter      # Read
    await asyncio.sleep(0)  # Context switch!
    counter = value + 1  # Write - may overwrite other increments

# RIGHT: Use asyncio.Lock
lock = asyncio.Lock()
counter = 0

async def increment():
    global counter
    async with lock:
        value = counter
        await asyncio.sleep(0)
        counter = value + 1
```

---

## Anti-Patterns

### 1. Awaiting in a Loop (Sequential)

```python
# WRONG: Sequential execution
async def fetch_all_users(user_ids: list[int]):
    users = []
    for user_id in user_ids:
        user = await fetch_user(user_id)  # Waits for each one
        users.append(user)
    return users
# Time: N * single_fetch_time

# RIGHT: Concurrent execution
async def fetch_all_users(user_ids: list[int]):
    tasks = [fetch_user(user_id) for user_id in user_ids]
    users = await asyncio.gather(*tasks)
    return users
# Time: max(single_fetch_time) ≈ single_fetch_time
```

### 2. Mixing Sync and Async Incorrectly

```python
# WRONG: Calling sync function that should be async
@app.get("/data")
async def get_data():
    # requests.get() blocks the event loop!
    response = requests.get("https://api.example.com")
    return response.json()

# WRONG: Using asyncio.run() inside async function
@app.get("/data")
async def get_data():
    # Can't nest event loops!
    result = asyncio.run(some_coroutine())  # RuntimeError
    return result
```

### 3. Not Handling Exceptions in Tasks

```python
# WRONG: Exception silently lost
async def background_job():
    raise ValueError("Something went wrong")

asyncio.create_task(background_job())  # No one sees the exception

# RIGHT: Handle task exceptions
async def safe_background_job():
    try:
        await background_job()
    except Exception as e:
        logger.exception("Background job failed")

# Or check task result
task = asyncio.create_task(background_job())
task.add_done_callback(lambda t: t.exception())  # Logs exception
```

### 4. Creating Too Many Concurrent Connections

```python
# WRONG: Opens thousands of connections simultaneously
urls = [f"https://api.example.com/{i}" for i in range(10000)]

async def fetch_all():
    async with httpx.AsyncClient() as client:
        tasks = [client.get(url) for url in urls]
        return await asyncio.gather(*tasks)  # 10000 connections!

# RIGHT: Limit concurrency
async def fetch_all():
    semaphore = asyncio.Semaphore(100)  # Max 100 concurrent
    
    async def fetch_one(client, url):
        async with semaphore:
            return await client.get(url)
    
    async with httpx.AsyncClient() as client:
        tasks = [fetch_one(client, url) for url in urls]
        return await asyncio.gather(*tasks)
```

---

## Production Patterns

### Graceful Shutdown

```python
import signal
from contextlib import asynccontextmanager

shutdown_event = asyncio.Event()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        shutdown_event.set()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    yield
    
    # Cleanup: wait for pending tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    
    await asyncio.gather(*tasks, return_exceptions=True)
```

### Connection Pool Management

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize connection pools
    app.state.db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=5,
        max_size=20
    )
    app.state.redis = await aioredis.from_url(
        REDIS_URL,
        max_connections=50
    )
    app.state.http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=100)
    )
    
    yield
    
    # Close pools
    await app.state.http_client.aclose()
    await app.state.redis.close()
    await app.state.db_pool.close()
```

### Health Checks with Async

```python
@app.get("/health")
async def health_check():
    checks = await asyncio.gather(
        check_database(),
        check_redis(),
        check_external_api(),
        return_exceptions=True
    )
    
    results = {
        "database": "ok" if not isinstance(checks[0], Exception) else "error",
        "redis": "ok" if not isinstance(checks[1], Exception) else "error",
        "external_api": "ok" if not isinstance(checks[2], Exception) else "error",
    }
    
    all_ok = all(v == "ok" for v in results.values())
    
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "healthy" if all_ok else "degraded", "checks": results}
    )
```

---

## Mastery Checkpoints

### Conceptual Questions

1. **What happens when you call `time.sleep(5)` inside an `async def` function?**

   *Answer*: It blocks the entire event loop for 5 seconds. No other coroutines can run during that time. All concurrent requests are stuck. Use `await asyncio.sleep(5)` instead, which yields control to the event loop.

2. **Why does FastAPI run `def` (sync) functions in a thread pool?**

   *Answer*: To prevent blocking the async event loop. The main event loop stays responsive handling other async operations, while the sync function runs in a separate thread. This lets you use blocking libraries without freezing your entire application.

3. **When would you use `asyncio.gather` vs `asyncio.create_task`?**

   *Answer*: `gather` when you need to wait for all results before continuing - like fetching data from multiple sources before returning a response. `create_task` when you want to fire-and-forget - like sending analytics that shouldn't delay the response. Also use `create_task` when you need more control over individual tasks.

4. **What's the danger of creating too many concurrent connections?**

   *Answer*: Resource exhaustion on both client and server. The target server may rate-limit or crash. Your application may run out of file descriptors. Networks may get congested. Use semaphores or connection pool limits to control concurrency.

5. **How does async improve throughput without improving single-request latency?**

   *Answer*: A single request still takes the same time (latency). But while that request waits for I/O, the server can start processing other requests. Instead of one request at a time per worker, you handle hundreds concurrently. Total requests per second (throughput) increases dramatically.

### Scenario Questions

6. **Design an async function that fetches user data from database, their recent orders, and recommendations from ML service, returning all three.**

   *Answer*:
   ```python
   async def get_user_dashboard(user_id: int):
       # All three are independent, run concurrently
       user, orders, recommendations = await asyncio.gather(
           db.get_user(user_id),
           db.get_recent_orders(user_id, limit=10),
           ml_service.get_recommendations(user_id),
           return_exceptions=True  # Don't fail if ML service is down
       )
       
       return {
           "user": user if not isinstance(user, Exception) else None,
           "orders": orders if not isinstance(orders, Exception) else [],
           "recommendations": recommendations if not isinstance(recommendations, Exception) else [],
           "errors": [str(e) for e in [user, orders, recommendations] if isinstance(e, Exception)]
       }
   ```

7. **You need to call an external API for each of 1000 items, but the API has a rate limit of 100 requests/second. How do you handle this?**

   *Answer*:
   ```python
   import asyncio
   
   async def fetch_with_rate_limit(items: list):
       semaphore = asyncio.Semaphore(100)  # Max 100 concurrent
       results = []
       
       async def fetch_one(item):
           async with semaphore:
               result = await external_api.fetch(item)
               await asyncio.sleep(0.01)  # Small delay to stay under rate limit
               return result
       
       # Process in batches to manage memory
       batch_size = 100
       for i in range(0, len(items), batch_size):
           batch = items[i:i + batch_size]
           batch_results = await asyncio.gather(
               *[fetch_one(item) for item in batch]
           )
           results.extend(batch_results)
           await asyncio.sleep(1)  # Ensure we stay under 100/second
       
       return results
   ```

8. **How do you make a blocking library (like a PDF generator) work in an async FastAPI endpoint?**

   *Answer*:
   ```python
   from concurrent.futures import ThreadPoolExecutor
   import asyncio
   
   pdf_executor = ThreadPoolExecutor(max_workers=4)
   
   def generate_pdf_sync(data: dict) -> bytes:
       """Blocking PDF generation"""
       from reportlab.lib import ...
       # ... generate PDF ...
       return pdf_bytes
   
   async def generate_pdf(data: dict) -> bytes:
       """Async wrapper around blocking PDF generation"""
       loop = asyncio.get_event_loop()
       pdf_bytes = await loop.run_in_executor(
           pdf_executor,
           generate_pdf_sync,
           data
       )
       return pdf_bytes
   
   @app.post("/reports/pdf")
   async def create_pdf_report(request: ReportRequest):
       pdf_bytes = await generate_pdf(request.data)
       return Response(
           content=pdf_bytes,
           media_type="application/pdf"
       )
   ```

9. **Your endpoint needs to call 5 external services. If any one fails, you should still return partial results. How?**

   *Answer*:
   ```python
   @app.get("/aggregated")
   async def get_aggregated():
       results = await asyncio.gather(
           service_a.fetch(),
           service_b.fetch(),
           service_c.fetch(),
           service_d.fetch(),
           service_e.fetch(),
           return_exceptions=True
       )
       
       response = {}
       errors = []
       
       services = ['a', 'b', 'c', 'd', 'e']
       for service, result in zip(services, results):
           if isinstance(result, Exception):
               errors.append({"service": service, "error": str(result)})
               response[service] = None
           else:
               response[service] = result
       
       return {
           "data": response,
           "errors": errors,
           "partial": len(errors) > 0
       }
   ```

10. **How do you implement a timeout for a complex async operation that involves multiple steps?**

    *Answer*:
    ```python
    async def complex_operation(user_id: int):
        """Multi-step operation that might be slow"""
        user = await db.get_user(user_id)
        orders = await db.get_orders(user_id)
        analytics = await compute_analytics(orders)
        return {"user": user, "orders": orders, "analytics": analytics}
    
    @app.get("/user/{user_id}/full")
    async def get_user_full(user_id: int):
        try:
            result = await asyncio.wait_for(
                complex_operation(user_id),
                timeout=10.0  # 10 second timeout for entire operation
            )
            return result
        except asyncio.TimeoutError:
            # Return partial data or error
            return JSONResponse(
                status_code=504,
                content={"error": "Operation timed out", "timeout_seconds": 10}
            )
    ```

---

## Interview Framing

When discussing async in interviews:

1. **Explain the mental model**: "Async is about efficient I/O waiting. While one request waits for a database response, the event loop runs other requests. It's not about parallelism—it's about not wasting time waiting."

2. **Show awareness of pitfalls**: "The biggest mistake is calling blocking code inside async functions. I always check if libraries are async-compatible. If not, I use sync handlers so FastAPI runs them in the thread pool."

3. **Discuss practical optimization**: "I identify independent operations and run them concurrently with gather. A dashboard endpoint that fetches user data, notifications, and analytics can run all three at once, cutting latency from 300ms to 100ms."

4. **Connect to system design**: "Async is essential for high-throughput APIs. A sync server with 10 workers handles 10 concurrent requests. An async server handles thousands. This affects how I design for scale."

5. **Mention debugging**: "I enable async debug mode during development to catch blocking calls. I also add timing logs around await points to identify slow operations in production."
