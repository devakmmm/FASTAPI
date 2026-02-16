# File: backend_fastapi_mastery/08_background_tasks_and_workers.md

# Background Tasks and Workers

## Why Background Processing?

Some operations shouldn't block API responses:
- Sending emails (2-5 seconds)
- Processing uploads (seconds to minutes)
- Generating reports (minutes)
- Syncing with external systems (variable)
- Expensive computations (variable)

Making users wait for these degrades experience and wastes server resources.

---

## FastAPI BackgroundTasks

### Basic Usage

```python
from fastapi import BackgroundTasks, FastAPI

app = FastAPI()

def send_email(email: str, message: str):
    """Runs after response is sent"""
    # Simulate email sending
    import time
    time.sleep(2)  # This doesn't block the response!
    print(f"Email sent to {email}")

@app.post("/register")
async def register_user(
    email: str,
    background_tasks: BackgroundTasks
):
    # Create user synchronously
    user = create_user(email)
    
    # Queue email for background - doesn't block response
    background_tasks.add_task(send_email, email, "Welcome!")
    
    return {"user_id": user.id}  # Returns immediately
```

### Async Background Tasks

```python
async def send_email_async(email: str, message: str):
    """Async background task"""
    async with httpx.AsyncClient() as client:
        await client.post("https://email-api.example.com/send", json={
            "to": email,
            "message": message
        })

@app.post("/orders")
async def create_order(
    order: OrderCreate,
    background_tasks: BackgroundTasks
):
    db_order = await order_service.create(order)
    
    # Async task
    background_tasks.add_task(
        send_email_async,
        order.customer_email,
        f"Order {db_order.id} confirmed!"
    )
    
    # Can add multiple tasks
    background_tasks.add_task(update_inventory_cache, db_order.items)
    background_tasks.add_task(notify_warehouse, db_order)
    
    return db_order
```

### How BackgroundTasks Work

```
Request arrives
       │
       ▼
┌──────────────────┐
│ Process Request  │
│ Add tasks to     │
│ background queue │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Return Response  │ ← User gets response here
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Run Background   │ ← Tasks run after response sent
│ Tasks            │
└──────────────────┘
```

### BackgroundTasks Limitations

**Runs in same process:**
- If server restarts, queued tasks are lost
- Can't distribute across multiple servers
- Shares resources with request handling

**Good for:**
- Quick, non-critical tasks
- Logging, analytics
- Cache updates
- Simple notifications

**Bad for:**
- Long-running tasks (> 30 seconds)
- Tasks that must complete (payments, critical updates)
- Tasks needing retry on failure
- High-volume task processing

---

## Lifespan Background Tasks

### Startup Tasks

```python
from contextlib import asynccontextmanager
import asyncio

# Global reference to background task
background_task: asyncio.Task | None = None

async def periodic_cleanup():
    """Runs periodically in background"""
    while True:
        try:
            await cleanup_expired_sessions()
            await asyncio.sleep(300)  # Every 5 minutes
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            await asyncio.sleep(60)  # Retry after 1 minute

@asynccontextmanager
async def lifespan(app: FastAPI):
    global background_task
    
    # Start background task
    background_task = asyncio.create_task(periodic_cleanup())
    
    yield
    
    # Shutdown: Cancel background task
    if background_task:
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass

app = FastAPI(lifespan=lifespan)
```

### Multiple Background Tasks

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start multiple background workers
    tasks = [
        asyncio.create_task(cache_warmer()),
        asyncio.create_task(metrics_reporter()),
        asyncio.create_task(health_checker()),
        asyncio.create_task(queue_processor()),
    ]
    
    yield
    
    # Shutdown all
    for task in tasks:
        task.cancel()
    
    await asyncio.gather(*tasks, return_exceptions=True)
```

---

## Scheduler Loops

### Time-Based Scheduling

```python
from datetime import datetime, timedelta
import asyncio

async def scheduled_report_generator():
    """Generate daily reports at midnight"""
    while True:
        now = datetime.now()
        
        # Calculate time until next midnight
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        wait_seconds = (tomorrow - now).total_seconds()
        
        await asyncio.sleep(wait_seconds)
        
        try:
            await generate_daily_reports()
        except Exception as e:
            logger.error(f"Report generation failed: {e}")

async def periodic_sync(interval_seconds: int = 60):
    """Sync every N seconds"""
    while True:
        try:
            await sync_with_external_system()
        except Exception as e:
            logger.error(f"Sync failed: {e}")
        
        await asyncio.sleep(interval_seconds)
```

### Cron-Like Scheduling

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Add jobs
    scheduler.add_job(
        daily_cleanup,
        CronTrigger(hour=2, minute=0),  # 2:00 AM daily
        id="daily_cleanup"
    )
    
    scheduler.add_job(
        hourly_sync,
        CronTrigger(minute=0),  # Every hour at :00
        id="hourly_sync"
    )
    
    scheduler.add_job(
        weekly_report,
        CronTrigger(day_of_week="mon", hour=9),  # Monday 9 AM
        id="weekly_report"
    )
    
    scheduler.start()
    
    yield
    
    scheduler.shutdown()
```

---

## Celery: Distributed Task Queue

### When to Use Celery

- Tasks that must survive server restarts
- Distribute work across multiple workers
- Tasks needing retry with backoff
- Schedule recurring tasks
- Long-running tasks (minutes to hours)
- High-volume task processing

### Celery Setup

```python
# celery_app.py
from celery import Celery

celery_app = Celery(
    "worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1"
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    task_soft_time_limit=3540,  # Warn at 59 minutes
)
```

### Defining Tasks

```python
# tasks.py
from celery_app import celery_app
import time

@celery_app.task(bind=True, max_retries=3)
def send_email_task(self, email: str, subject: str, body: str):
    try:
        send_email(email, subject, body)
    except EmailServiceError as e:
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries)

@celery_app.task(bind=True)
def process_video_task(self, video_id: int):
    """Long-running task with progress updates"""
    video = get_video(video_id)
    
    # Update state for monitoring
    self.update_state(state="PROCESSING", meta={"progress": 0})
    
    for i, frame in enumerate(video.frames):
        process_frame(frame)
        
        progress = (i + 1) / len(video.frames) * 100
        self.update_state(state="PROCESSING", meta={"progress": progress})
    
    return {"video_id": video_id, "status": "completed"}

@celery_app.task
def generate_report_task(report_type: str, params: dict):
    """Task returning result"""
    report = generate_report(report_type, params)
    save_report(report)
    return {"report_id": report.id, "url": report.url}
```

### Calling Celery Tasks from FastAPI

```python
from tasks import send_email_task, generate_report_task

@app.post("/users")
async def create_user(user: UserCreate):
    db_user = await user_repo.create(user)
    
    # Queue task - returns immediately
    send_email_task.delay(
        email=user.email,
        subject="Welcome!",
        body="Thanks for signing up"
    )
    
    return db_user

@app.post("/reports")
async def request_report(request: ReportRequest):
    # Queue task and get task ID
    task = generate_report_task.delay(
        report_type=request.type,
        params=request.params
    )
    
    return {
        "task_id": task.id,
        "status_url": f"/tasks/{task.id}"
    }

@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    task = generate_report_task.AsyncResult(task_id)
    
    if task.state == "PENDING":
        return {"status": "pending"}
    elif task.state == "PROCESSING":
        return {"status": "processing", "progress": task.info.get("progress", 0)}
    elif task.state == "SUCCESS":
        return {"status": "completed", "result": task.result}
    elif task.state == "FAILURE":
        return {"status": "failed", "error": str(task.result)}
    
    return {"status": task.state}
```

### Celery Retry Patterns

```python
@celery_app.task(
    bind=True,
    max_retries=5,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,  # Exponential backoff
    retry_backoff_max=600,  # Max 10 minutes
    retry_jitter=True  # Add randomness
)
def reliable_external_call(self, data: dict):
    response = external_api.call(data)
    return response

# Manual retry with custom logic
@celery_app.task(bind=True, max_retries=3)
def smart_retry_task(self, order_id: int):
    try:
        process_order(order_id)
    except TransientError as e:
        # Retry with increasing delay
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
    except PermanentError as e:
        # Don't retry - log and alert
        logger.error(f"Permanent failure for order {order_id}: {e}")
        alert_team(f"Order {order_id} failed permanently")
        raise
```

---

## Simple Polling vs Celery

### Simple Polling Pattern

For simpler needs without Celery infrastructure:

```python
import asyncio
from datetime import datetime, timedelta

class SimpleTaskQueue:
    """In-memory task queue with polling"""
    
    def __init__(self):
        self.tasks: asyncio.Queue = asyncio.Queue()
        self.results: dict = {}
        self._running = False
    
    async def enqueue(self, task_id: str, func, *args, **kwargs):
        await self.tasks.put((task_id, func, args, kwargs))
        self.results[task_id] = {"status": "pending"}
        return task_id
    
    async def get_status(self, task_id: str) -> dict:
        return self.results.get(task_id, {"status": "not_found"})
    
    async def worker(self):
        """Process tasks from queue"""
        self._running = True
        while self._running:
            try:
                task_id, func, args, kwargs = await asyncio.wait_for(
                    self.tasks.get(),
                    timeout=1.0
                )
                
                self.results[task_id] = {"status": "processing"}
                
                try:
                    if asyncio.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    
                    self.results[task_id] = {
                        "status": "completed",
                        "result": result
                    }
                except Exception as e:
                    self.results[task_id] = {
                        "status": "failed",
                        "error": str(e)
                    }
            except asyncio.TimeoutError:
                continue
    
    def stop(self):
        self._running = False

# Global queue
task_queue = SimpleTaskQueue()

@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(task_queue.worker())
    yield
    task_queue.stop()
    worker_task.cancel()
```

### Database-Backed Task Queue

More durable than in-memory:

```python
from sqlalchemy import Column, Integer, String, JSON, DateTime, Enum
import enum

class TaskStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    result = Column(JSON, nullable=True)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

class TaskProcessor:
    def __init__(self, db_session_factory):
        self.session_factory = db_session_factory
        self.handlers: dict = {}
    
    def register(self, task_type: str, handler):
        self.handlers[task_type] = handler
    
    async def process_pending_tasks(self):
        """Poll for and process pending tasks"""
        async with self.session_factory() as session:
            # Get pending tasks (with locking to prevent double-processing)
            result = await session.execute(
                select(Task)
                .where(Task.status == TaskStatus.PENDING)
                .limit(10)
                .with_for_update(skip_locked=True)  # Skip locked rows
            )
            tasks = result.scalars().all()
            
            for task in tasks:
                await self._process_task(session, task)
    
    async def _process_task(self, session, task: Task):
        handler = self.handlers.get(task.type)
        if not handler:
            task.status = TaskStatus.FAILED
            task.error = f"Unknown task type: {task.type}"
            await session.commit()
            return
        
        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.utcnow()
        await session.commit()
        
        try:
            result = await handler(task.payload)
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = datetime.utcnow()
        except Exception as e:
            if task.retry_count < task.max_retries:
                task.status = TaskStatus.PENDING
                task.retry_count += 1
            else:
                task.status = TaskStatus.FAILED
                task.error = str(e)
        
        await session.commit()
```

---

## When to Use Which

| Pattern | Use Case | Pros | Cons |
|---------|----------|------|------|
| **BackgroundTasks** | Quick, non-critical tasks | Simple, no infrastructure | Lost on restart, same process |
| **Lifespan Tasks** | Periodic cleanup, monitoring | Part of app lifecycle | Same process, no distribution |
| **Simple Polling** | Moderate task volume | Simple, controllable | Single process, limited scale |
| **DB Task Queue** | Durable tasks, moderate scale | Survives restarts, visibility | DB load, still single process |
| **Celery** | High volume, distributed | Scalable, robust, features | Complex infrastructure |
| **Redis Queue (RQ)** | Simpler than Celery | Simpler setup | Less features than Celery |

### Decision Tree

```
Is the task critical (must complete)?
├── No → BackgroundTasks
└── Yes
    │
    ├── Does it need to survive server restarts?
    │   ├── No → BackgroundTasks with error handling
    │   └── Yes → DB Queue or Celery
    │
    ├── Is task volume high (>1000/min)?
    │   ├── No → DB Queue
    │   └── Yes → Celery
    │
    └── Do you need distributed processing?
        ├── No → DB Queue
        └── Yes → Celery
```

---

## Production Patterns

### Task Deduplication

```python
import hashlib
import json

async def enqueue_with_dedup(
    task_type: str,
    payload: dict,
    dedup_window_seconds: int = 300
):
    """Prevent duplicate task submission"""
    # Create deterministic hash of task
    task_hash = hashlib.sha256(
        json.dumps({"type": task_type, "payload": payload}, sort_keys=True).encode()
    ).hexdigest()
    
    # Check if already submitted recently
    existing = await redis.get(f"task_dedup:{task_hash}")
    if existing:
        return {"status": "duplicate", "task_id": existing}
    
    # Submit task
    task_id = await task_queue.enqueue(task_type, payload)
    
    # Mark as submitted
    await redis.set(
        f"task_dedup:{task_hash}",
        task_id,
        ex=dedup_window_seconds
    )
    
    return {"status": "queued", "task_id": task_id}
```

### Priority Queues

```python
# Celery with priority queues
celery_app.conf.task_routes = {
    "tasks.critical_*": {"queue": "critical"},
    "tasks.normal_*": {"queue": "normal"},
    "tasks.bulk_*": {"queue": "bulk"},
}

# Start workers for different queues
# celery -A tasks worker -Q critical -c 10
# celery -A tasks worker -Q normal -c 5
# celery -A tasks worker -Q bulk -c 2

@celery_app.task(queue="critical")
def critical_payment_task(payment_id: int):
    """High priority - more workers"""
    process_payment(payment_id)

@celery_app.task(queue="bulk")
def bulk_email_task(user_ids: list):
    """Low priority - fewer workers"""
    send_bulk_emails(user_ids)
```

### Dead Letter Queue

```python
class TaskQueue:
    async def process_task(self, task):
        try:
            await self._execute(task)
        except Exception as e:
            if task.retry_count >= task.max_retries:
                # Move to dead letter queue
                await self.move_to_dlq(task, error=str(e))
            else:
                # Retry
                task.retry_count += 1
                await self.requeue(task, delay=self._backoff(task.retry_count))
    
    async def move_to_dlq(self, task, error: str):
        """Store failed tasks for manual review"""
        await db.execute(
            insert(DeadLetterTask).values(
                original_task_id=task.id,
                task_type=task.type,
                payload=task.payload,
                error=error,
                retry_count=task.retry_count,
                failed_at=datetime.utcnow()
            )
        )
        
        # Alert
        await alert_service.send(
            f"Task {task.id} moved to DLQ after {task.retry_count} retries: {error}"
        )
```

### Monitoring Background Tasks

```python
import prometheus_client as prom

# Metrics
tasks_processed = prom.Counter(
    "tasks_processed_total",
    "Total tasks processed",
    ["task_type", "status"]
)

task_duration = prom.Histogram(
    "task_duration_seconds",
    "Task processing duration",
    ["task_type"]
)

tasks_queued = prom.Gauge(
    "tasks_queued",
    "Current number of queued tasks",
    ["task_type"]
)

async def process_task_with_metrics(task):
    start_time = time.time()
    status = "success"
    
    try:
        await execute_task(task)
    except Exception:
        status = "failure"
        raise
    finally:
        duration = time.time() - start_time
        tasks_processed.labels(task_type=task.type, status=status).inc()
        task_duration.labels(task_type=task.type).observe(duration)
```

---

## Mastery Checkpoints

### Conceptual Questions

1. **When would you use FastAPI BackgroundTasks vs Celery?**

   *Answer*: BackgroundTasks for quick, non-critical tasks (analytics, logging, non-essential notifications) that can be lost on restart. Celery for tasks that must complete (payments, order processing), need retries, require distribution across workers, or are long-running.

2. **What happens if a BackgroundTask fails?**

   *Answer*: It raises an exception that's logged but not propagated to the user (response already sent). The task is lost - no automatic retry. For critical tasks, use proper task queues with retry mechanisms.

3. **Why use exponential backoff with jitter for task retries?**

   *Answer*: Exponential backoff prevents overwhelming a recovering service. Jitter (randomness) prevents thundering herd - without it, all failed tasks would retry at exactly the same time, potentially crashing the service again.

4. **How do you prevent the same task from being processed twice?**

   *Answer*: Use distributed locks (Redis SETNX), database row locking (SELECT FOR UPDATE SKIP LOCKED), or idempotency keys. Track processed task IDs temporarily to reject duplicates. Design tasks to be idempotent when possible.

5. **What's a dead letter queue and why do you need it?**

   *Answer*: A DLQ stores tasks that failed after all retries. Without it, permanently failing tasks disappear silently. DLQ provides visibility into failures, allows manual inspection and replay, and prevents infinite retry loops for bad data.

### Scenario Questions

6. **Design a system to send 1 million marketing emails without blocking your API.**

   *Answer*:
   ```python
   @app.post("/campaigns/{campaign_id}/send")
   async def send_campaign(campaign_id: int):
       campaign = await campaign_repo.get(campaign_id)
       recipients = await get_campaign_recipients(campaign_id)  # 1M users
       
       # Don't create 1M individual tasks - batch them
       batch_size = 1000
       for i in range(0, len(recipients), batch_size):
           batch = recipients[i:i + batch_size]
           send_email_batch.delay(
               campaign_id=campaign_id,
               recipient_ids=[r.id for r in batch]
           )
       
       return {"status": "queued", "batches": len(recipients) // batch_size}
   
   @celery_app.task(
       rate_limit="100/m",  # Don't overwhelm email service
       autoretry_for=(EmailServiceError,),
       retry_backoff=True
   )
   def send_email_batch(campaign_id: int, recipient_ids: list):
       campaign = get_campaign(campaign_id)
       for recipient_id in recipient_ids:
           recipient = get_user(recipient_id)
           send_email(recipient.email, campaign.subject, campaign.body)
   ```

7. **Your order processing task occasionally fails due to payment provider issues. How do you handle this?**

   *Answer*:
   ```python
   @celery_app.task(bind=True, max_retries=5)
   def process_order(self, order_id: int):
       order = get_order(order_id)
       
       # Idempotency check
       if order.status == "completed":
           return {"status": "already_completed"}
       
       try:
           # Attempt payment
           payment = payment_service.charge(
               amount=order.total,
               idempotency_key=f"order_{order_id}"
           )
           
           # Update order
           order.payment_id = payment.id
           order.status = "completed"
           save_order(order)
           
           # Queue non-critical follow-ups
           send_confirmation.delay(order_id)
           update_inventory.delay(order_id)
           
       except PaymentDeclinedError:
           # Don't retry - user's card was declined
           order.status = "payment_failed"
           save_order(order)
           notify_user_payment_failed.delay(order_id)
           
       except PaymentServiceError as e:
           # Transient error - retry
           order.status = "payment_pending"
           save_order(order)
           raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
   ```

8. **How do you handle long-running tasks (30+ minutes) in a way that users can track progress?**

   *Answer*:
   ```python
   @celery_app.task(bind=True)
   def generate_large_report(self, report_id: int):
       report = get_report(report_id)
       total_steps = 100
       
       for i in range(total_steps):
           # Update progress
           self.update_state(
               state="PROCESSING",
               meta={"progress": i + 1, "total": total_steps}
           )
           
           # Process step
           process_report_step(report, i)
       
       # Save final result
       report.status = "completed"
       report.file_url = upload_report(report)
       save_report(report)
       
       return {"report_id": report_id, "url": report.file_url}
   
   @app.get("/reports/{report_id}/status")
   async def get_report_status(report_id: int):
       report = await report_repo.get(report_id)
       
       if report.celery_task_id:
           task = generate_large_report.AsyncResult(report.celery_task_id)
           if task.state == "PROCESSING":
               return {
                   "status": "processing",
                   "progress": task.info.get("progress", 0),
                   "total": task.info.get("total", 100)
               }
       
       return {"status": report.status, "url": report.file_url}
   ```

9. **You need to process tasks in order (FIFO) for each user, but can process different users in parallel. How?**

   *Answer*:
   ```python
   # Use task chains per user
   from celery import chain
   
   def queue_user_tasks(user_id: int, tasks: list):
       """Queue tasks as a chain for ordering"""
       task_chain = chain(
           *(process_task.s(task_data) for task_data in tasks)
       )
       task_chain.apply_async(queue=f"user_{user_id}")
   
   # Or use dedicated queues per user with single concurrency
   # Start workers: celery -A app worker -Q user_1,user_2 -c 1
   
   # Or implement ordering in task
   @celery_app.task(bind=True)
   def ordered_task(self, user_id: int, sequence_number: int, data: dict):
       # Wait for previous task to complete
       expected_seq = get_last_completed_sequence(user_id) + 1
       if sequence_number > expected_seq:
           # Not our turn yet - requeue
           raise self.retry(countdown=5)
       
       # Process
       process_data(data)
       mark_sequence_completed(user_id, sequence_number)
   ```

10. **Your background worker processes payments. How do you ensure exactly-once processing?**

    *Answer*:
    ```python
    @celery_app.task(bind=True)
    def process_payment(self, payment_id: int):
        # 1. Lock the payment record
        with db.begin():
            payment = db.query(Payment).filter_by(id=payment_id).with_for_update().one()
            
            # 2. Check if already processed (idempotency)
            if payment.status in ("completed", "failed"):
                return {"status": "already_processed", "payment_id": payment_id}
            
            # 3. Mark as processing
            payment.status = "processing"
            payment.task_id = self.request.id
            db.commit()
        
        # 4. Call payment provider with idempotency key
        try:
            result = stripe.charges.create(
                amount=payment.amount,
                customer=payment.customer_id,
                idempotency_key=f"payment_{payment_id}"
            )
            
            payment.status = "completed"
            payment.provider_id = result.id
            
        except stripe.CardError:
            payment.status = "failed"
            payment.error = "Card declined"
        
        db.commit()
        return {"status": payment.status}
    ```

---

## Interview Framing

When discussing background tasks:

1. **Show understanding of trade-offs**: "BackgroundTasks is simple but tasks are lost on restart. For payment processing, I use Celery with Redis because tasks must survive failures and support retries."

2. **Discuss durability**: "I separate critical vs non-critical tasks. Order confirmations are critical - they go to Celery with persistence. Analytics events are non-critical - BackgroundTasks is fine."

3. **Explain scaling**: "For high volume, I use Celery with multiple queues. Critical tasks get dedicated workers with high concurrency. Bulk operations get separate workers so they don't impact real-time operations."

4. **Mention monitoring**: "I track queue depth, processing time, and failure rates. If the queue grows faster than processing, I scale workers. I alert on elevated failure rates."

5. **Connect to user experience**: "Long operations return immediately with a job ID. Users poll for status or get webhooks. They see progress updates, not hanging requests."
