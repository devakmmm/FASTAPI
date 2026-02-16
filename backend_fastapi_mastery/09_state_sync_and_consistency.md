# File: backend_fastapi_mastery/09_state_sync_and_consistency.md

# State Sync and Consistency

## Why This Matters

In distributed systems, data exists in multiple places:
- Your database
- External service databases
- Caches (Redis, Memcached)
- Search indexes (Elasticsearch)
- CDNs

These copies get out of sync. Understanding consistency models and sync strategies is essential for building reliable systems.

---

## Consistency Models

### Strong Consistency

**After a write, all subsequent reads return the new value.**

```
Write: x = 5
        │
        ▼
   ┌─────────┐
   │ Database│
   └────┬────┘
        │
        ▼
Read: returns 5  ← Guaranteed, always
```

**Example**: Bank balance after transfer

```python
async def transfer(from_account: int, to_account: int, amount: Decimal):
    async with db.begin():  # Transaction
        # These reads see the freshest data
        from_acc = await db.get(Account, from_account, with_for_update=True)
        to_acc = await db.get(Account, to_account, with_for_update=True)
        
        from_acc.balance -= amount
        to_acc.balance += amount
        
        # After commit, anyone reading sees new balances
        await db.commit()
```

**Trade-offs:**
- Higher latency (must wait for write confirmation)
- Lower availability (if primary is down, writes blocked)
- Required for: Financial transactions, inventory counts, unique constraints

### Eventual Consistency

**After a write, reads will eventually return the new value, but may return stale data temporarily.**

```
Write: x = 5
        │
        ▼
   ┌─────────┐
   │ Primary │
   └────┬────┘
        │ (replication lag: 10-100ms)
        ▼
   ┌─────────┐
   │ Replica │
   └────┬────┘
        │
        ▼
Read: might return 4 (old) or 5 (new)
```

**Example**: Social media feed

```python
async def post_update(user_id: int, content: str):
    # Write to primary
    post = await db.create(Post(user_id=user_id, content=content))
    
    # Async update to cache, search index
    await cache.delete(f"user:{user_id}:feed")  # Invalidate cache
    await search_index.index(post)  # Update search
    
    return post

async def get_feed(user_id: int):
    # May read from replica - could be slightly behind
    posts = await db.replica.query(
        select(Post).where(Post.user_id.in_(following_ids)).limit(50)
    )
    return posts
```

**Trade-offs:**
- Lower latency (can read from replicas)
- Higher availability (replicas can serve reads if primary down)
- Acceptable for: Feeds, search results, analytics, caches

### Read Your Own Writes

**A user sees their own writes immediately, even if other users see eventual consistency.**

```python
async def create_post(user_id: int, content: str, session_id: str):
    post = await db.primary.create(Post(...))
    
    # Cache the write timestamp
    await redis.set(
        f"user:{user_id}:last_write",
        time.time(),
        ex=60
    )
    
    return post

async def get_feed(user_id: int, session_id: str):
    last_write = await redis.get(f"user:{user_id}:last_write")
    
    if last_write and time.time() - float(last_write) < 5:
        # Recent write - read from primary to ensure we see it
        return await db.primary.query(...)
    else:
        # Safe to read from replica
        return await db.replica.query(...)
```

---

## On-Demand Sync vs Background Sync

### On-Demand Sync

**Fetch fresh data from external source when requested.**

```python
async def get_payment_status(payment_id: int) -> PaymentStatus:
    # Check local cache first
    cached = await cache.get(f"payment:{payment_id}")
    if cached:
        return PaymentStatus.parse_raw(cached)
    
    # Fetch from external API
    external_status = await stripe_client.get_payment(payment_id)
    
    # Update local database
    await db.execute(
        update(Payment)
        .where(Payment.id == payment_id)
        .values(
            status=external_status.status,
            last_synced_at=datetime.utcnow()
        )
    )
    
    # Cache for subsequent requests
    await cache.set(
        f"payment:{payment_id}",
        external_status.json(),
        ex=60
    )
    
    return external_status
```

**When to use:**
- Data changes frequently
- External API is fast and reliable
- Freshness is critical
- Volume is manageable

### Background Sync

**Periodically sync data in background, serve from local copy.**

```python
# Background sync job
async def sync_payments():
    """Runs every 5 minutes"""
    # Get payments that need syncing
    stale_payments = await db.query(
        select(Payment)
        .where(Payment.status == "pending")
        .where(Payment.last_synced_at < datetime.utcnow() - timedelta(minutes=5))
        .limit(100)
    )
    
    for payment in stale_payments:
        try:
            external = await stripe_client.get_payment(payment.stripe_id)
            
            payment.status = external.status
            payment.last_synced_at = datetime.utcnow()
            
            if external.status in ("succeeded", "failed"):
                # Final state - trigger webhooks
                await notify_payment_complete(payment)
        
        except Exception as e:
            logger.error(f"Sync failed for payment {payment.id}: {e}")
    
    await db.commit()

# API serves from local database (fast)
async def get_payment_status(payment_id: int) -> Payment:
    return await db.get(Payment, payment_id)
```

**When to use:**
- External API is slow or rate-limited
- Data can be slightly stale
- High read volume
- Bulk synchronization needed

### Hybrid Approach

```python
async def get_payment_status(payment_id: int) -> Payment:
    payment = await db.get(Payment, payment_id)
    
    # If status is pending and stale, refresh on-demand
    if (
        payment.status == "pending" and
        payment.last_synced_at < datetime.utcnow() - timedelta(minutes=1)
    ):
        # Trigger background refresh, return current data
        await background_tasks.add_task(sync_single_payment, payment_id)
    
    # If user is actively waiting for completion, sync immediately
    if payment.status == "pending" and payment.is_user_waiting:
        try:
            external = await stripe_client.get_payment(payment.stripe_id)
            if external.status != payment.status:
                payment.status = external.status
                payment.last_synced_at = datetime.utcnow()
                await db.commit()
        except Exception:
            pass  # Return cached data on failure
    
    return payment
```

---

## Race Conditions

### The Problem

```
Thread A                    Thread B
   │                           │
   ├── Read inventory: 10      │
   │                           ├── Read inventory: 10
   │                           │
   ├── inventory - 1 = 9       │
   │                           ├── inventory - 1 = 9
   │                           │
   ├── Write: 9                │
   │                           ├── Write: 9  ← Lost update!
   │                           │
   ▼                           ▼
   
Actual inventory should be 8, but it's 9
```

### Solution 1: Optimistic Locking

```python
class Product(Base):
    id = Column(Integer, primary_key=True)
    stock = Column(Integer, nullable=False)
    version = Column(Integer, default=1)  # Version for optimistic locking

async def decrease_stock(product_id: int, quantity: int):
    # Read current state
    product = await db.get(Product, product_id)
    current_version = product.version
    
    if product.stock < quantity:
        raise InsufficientStockError()
    
    # Update with version check
    result = await db.execute(
        update(Product)
        .where(Product.id == product_id)
        .where(Product.version == current_version)  # Check version unchanged
        .values(
            stock=Product.stock - quantity,
            version=Product.version + 1
        )
    )
    
    if result.rowcount == 0:
        # Version changed - someone else modified
        raise ConcurrentModificationError("Stock was modified, please retry")
    
    await db.commit()
```

### Solution 2: Pessimistic Locking

```python
async def decrease_stock(product_id: int, quantity: int):
    async with db.begin():
        # Lock the row - other transactions wait
        product = await db.execute(
            select(Product)
            .where(Product.id == product_id)
            .with_for_update()  # Exclusive lock
        )
        product = product.scalar_one()
        
        if product.stock < quantity:
            raise InsufficientStockError()
        
        product.stock -= quantity
        await db.commit()
```

### Solution 3: Atomic Operations

```python
# Let the database handle atomicity
async def decrease_stock(product_id: int, quantity: int):
    result = await db.execute(
        update(Product)
        .where(Product.id == product_id)
        .where(Product.stock >= quantity)  # Constraint in query
        .values(stock=Product.stock - quantity)
    )
    
    if result.rowcount == 0:
        raise InsufficientStockError()
    
    await db.commit()
```

### Solution 4: Redis Atomic Operations

```python
async def decrease_stock_redis(product_id: int, quantity: int):
    # Lua script runs atomically
    lua_script = """
    local current = redis.call('GET', KEYS[1])
    if current == false then
        return {err = 'not_found'}
    end
    if tonumber(current) < tonumber(ARGV[1]) then
        return {err = 'insufficient'}
    end
    return redis.call('DECRBY', KEYS[1], ARGV[1])
    """
    
    result = await redis.eval(
        lua_script,
        keys=[f"stock:{product_id}"],
        args=[quantity]
    )
    
    if isinstance(result, dict) and "err" in result:
        raise InsufficientStockError()
    
    return result
```

---

## Stale Data

### Caching Strategies

**Cache-Aside (Lazy Loading)**
```python
async def get_user(user_id: int) -> User:
    # Try cache first
    cached = await cache.get(f"user:{user_id}")
    if cached:
        return User.parse_raw(cached)
    
    # Cache miss - load from DB
    user = await db.get(User, user_id)
    
    # Populate cache
    await cache.set(f"user:{user_id}", user.json(), ex=300)
    
    return user
```

**Write-Through**
```python
async def update_user(user_id: int, data: UserUpdate) -> User:
    # Update database
    user = await db.get(User, user_id)
    for key, value in data.dict(exclude_unset=True).items():
        setattr(user, key, value)
    await db.commit()
    
    # Update cache immediately
    await cache.set(f"user:{user_id}", user.json(), ex=300)
    
    return user
```

**Write-Behind (Async Write)**
```python
async def update_user(user_id: int, data: UserUpdate) -> User:
    # Update cache immediately
    user = await get_user(user_id)
    updated = user.copy(update=data.dict(exclude_unset=True))
    await cache.set(f"user:{user_id}", updated.json(), ex=300)
    
    # Queue database write for later
    await write_queue.enqueue(
        "update_user",
        {"user_id": user_id, "data": data.dict()}
    )
    
    return updated
```

### Cache Invalidation

```python
# Invalidate on write
async def update_product(product_id: int, data: ProductUpdate):
    await db.update(Product, product_id, data)
    await cache.delete(f"product:{product_id}")
    await cache.delete(f"products:category:{product.category_id}")  # Related caches

# Time-based expiration
await cache.set(f"user:{user_id}", data, ex=300)  # 5 minutes

# Event-based invalidation
@event_listener("product.updated")
async def invalidate_product_cache(event: ProductUpdatedEvent):
    await cache.delete(f"product:{event.product_id}")
    await cache.delete_pattern(f"search:*product*")
```

### Detecting Stale Data

```python
async def get_product_with_freshness(product_id: int) -> dict:
    # Get from cache with metadata
    cached = await cache.get(f"product:{product_id}")
    
    if cached:
        data = json.loads(cached)
        cached_at = datetime.fromisoformat(data["_cached_at"])
        age_seconds = (datetime.utcnow() - cached_at).total_seconds()
        
        return {
            "product": data["product"],
            "is_stale": age_seconds > 60,  # Stale after 1 minute
            "age_seconds": age_seconds
        }
    
    # Fresh from database
    product = await db.get(Product, product_id)
    
    await cache.set(
        f"product:{product_id}",
        json.dumps({
            "product": product.dict(),
            "_cached_at": datetime.utcnow().isoformat()
        }),
        ex=300
    )
    
    return {
        "product": product,
        "is_stale": False,
        "age_seconds": 0
    }
```

---

## Distributed System Reasoning

### The CAP Theorem

You can only have 2 of 3:
- **C**onsistency: All nodes see same data
- **A**vailability: Every request gets a response
- **P**artition tolerance: System works despite network failures

In practice, network partitions happen, so you choose between:
- **CP**: Consistent but may be unavailable (banks, inventory)
- **AP**: Available but may be inconsistent (social media, caches)

### Handling Network Partitions

```python
async def create_order_with_partition_handling(order: OrderCreate):
    try:
        # Try strong consistency path
        async with db.begin():
            # Verify inventory with lock
            product = await db.get(Product, order.product_id, with_for_update=True)
            if product.stock < order.quantity:
                raise InsufficientStockError()
            
            product.stock -= order.quantity
            order = await db.create(Order(...))
            await db.commit()
        
        return order
        
    except DatabaseUnavailableError:
        # Partition detected - switch to eventual consistency
        # Create order as "pending_verification"
        order = await create_pending_order(order)
        
        # Queue verification for when DB is available
        await task_queue.enqueue("verify_and_complete_order", order.id)
        
        return {"order_id": order.id, "status": "pending_verification"}
```

### Saga Pattern

For distributed transactions across services:

```python
async def checkout_saga(order: Order):
    """
    Saga: Each step has a compensating action.
    If any step fails, execute compensations in reverse order.
    """
    compensations = []
    
    try:
        # Step 1: Reserve inventory
        reservation = await inventory_service.reserve(order.items)
        compensations.append(lambda: inventory_service.release(reservation.id))
        
        # Step 2: Create payment hold
        payment_hold = await payment_service.authorize(order.total, order.customer_id)
        compensations.append(lambda: payment_service.cancel_auth(payment_hold.id))
        
        # Step 3: Create shipment
        shipment = await shipping_service.create_shipment(order)
        compensations.append(lambda: shipping_service.cancel(shipment.id))
        
        # Step 4: Capture payment (point of no return)
        payment = await payment_service.capture(payment_hold.id)
        
        # Step 5: Confirm reservation
        await inventory_service.confirm(reservation.id)
        
        return {"status": "completed", "order_id": order.id}
        
    except Exception as e:
        # Execute compensations in reverse order
        for compensate in reversed(compensations):
            try:
                await compensate()
            except Exception as comp_error:
                logger.error(f"Compensation failed: {comp_error}")
                # Alert for manual intervention
                await alert_service.send(f"Saga compensation failed: {order.id}")
        
        raise CheckoutError(f"Checkout failed: {e}")
```

### Idempotent Receivers

Handle duplicate messages in event-driven systems:

```python
async def handle_payment_completed_event(event: PaymentCompletedEvent):
    # Check if already processed (idempotency)
    processed = await redis.get(f"event:processed:{event.event_id}")
    if processed:
        logger.info(f"Event {event.event_id} already processed, skipping")
        return
    
    # Process the event
    await order_service.mark_paid(event.order_id)
    
    # Mark as processed
    await redis.set(
        f"event:processed:{event.event_id}",
        "1",
        ex=86400 * 7  # Keep for 7 days
    )
```

---

## Real-World Sync Patterns

### External API State Sync

```python
class PaymentSyncService:
    """Keeps local payment state in sync with Stripe"""
    
    async def sync_payment(self, payment_id: int):
        payment = await self.db.get(Payment, payment_id)
        
        if payment.status in ("succeeded", "failed"):
            # Final state - no need to sync
            return payment
        
        # Fetch from Stripe
        stripe_payment = await self.stripe_client.get(payment.stripe_id)
        
        # Update local state
        if stripe_payment.status != payment.status:
            payment.status = stripe_payment.status
            payment.last_synced_at = datetime.utcnow()
            
            # Trigger downstream updates
            if stripe_payment.status == "succeeded":
                await self.order_service.mark_paid(payment.order_id)
            elif stripe_payment.status == "failed":
                await self.order_service.mark_payment_failed(payment.order_id)
        
        await self.db.commit()
        return payment
    
    async def sync_all_pending(self):
        """Background job to sync all pending payments"""
        pending = await self.db.query(
            select(Payment)
            .where(Payment.status == "pending")
            .where(Payment.created_at > datetime.utcnow() - timedelta(days=7))
        )
        
        for payment in pending:
            try:
                await self.sync_payment(payment.id)
            except Exception as e:
                logger.error(f"Failed to sync payment {payment.id}: {e}")
```

### Webhook vs Polling

```python
# Webhook handler - instant notifications
@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    
    if event["type"] == "payment_intent.succeeded":
        await handle_payment_success(event["data"]["object"])
    elif event["type"] == "payment_intent.payment_failed":
        await handle_payment_failure(event["data"]["object"])
    
    return {"received": True}

# Polling backup - catches missed webhooks
async def poll_pending_payments():
    """Runs every 5 minutes as backup"""
    pending = await db.query(
        select(Payment)
        .where(Payment.status == "pending")
        .where(Payment.last_synced_at < datetime.utcnow() - timedelta(minutes=5))
    )
    
    for payment in pending:
        await sync_service.sync_payment(payment.id)
```

---

## Mastery Checkpoints

### Conceptual Questions

1. **What's the difference between strong and eventual consistency?**

   *Answer*: Strong consistency guarantees that after a write, all subsequent reads see the new value. Eventual consistency only guarantees that reads will eventually see the new value, but may return stale data temporarily. Strong consistency is needed for financial transactions; eventual is acceptable for social feeds.

2. **How do you handle the case where your local database and an external service's database disagree?**

   *Answer*: Treat the external service as the source of truth for its data. Sync periodically via background jobs and webhooks. For critical operations, verify with the external API before proceeding. Log discrepancies for investigation. Design for eventual consistency unless strong consistency is required.

3. **What causes a race condition and how do you prevent it?**

   *Answer*: Race conditions occur when multiple processes read-modify-write without synchronization, causing lost updates. Prevent with: (1) optimistic locking (version checks), (2) pessimistic locking (SELECT FOR UPDATE), (3) atomic database operations, (4) distributed locks for cross-service coordination.

4. **When would you choose optimistic vs pessimistic locking?**

   *Answer*: Optimistic: Low contention, conflicts are rare, reads don't need locks. Pessimistic: High contention, conflicts are likely, critical sections must not fail. Optimistic scales better but requires retry logic. Pessimistic is simpler but can cause lock contention.

5. **How does "read your own writes" consistency work?**

   *Answer*: Track recent writes per user/session. If a user recently wrote data, route their reads to the primary database to ensure they see their changes. Other users can read from replicas. This provides strong consistency for the user who wrote while maintaining high read scalability.

### Scenario Questions

6. **You're building an e-commerce inventory system. How do you handle concurrent purchases of the same product?**

   *Answer*:
   ```python
   async def purchase(product_id: int, quantity: int, user_id: int):
       # Use atomic decrement with constraint
       result = await db.execute(
           update(Product)
           .where(Product.id == product_id)
           .where(Product.stock >= quantity)  # Atomic check
           .values(stock=Product.stock - quantity)
           .returning(Product.stock)
       )
       
       if result.rowcount == 0:
           raise InsufficientStockError()
       
       # Create order
       order = await create_order(user_id, product_id, quantity)
       await db.commit()
       
       return order
   
   # Alternative with Redis for high-traffic:
   async def purchase_with_redis(product_id: int, quantity: int):
       # Atomic decrement in Redis
       new_stock = await redis.decrby(f"stock:{product_id}", quantity)
       
       if new_stock < 0:
           # Rollback
           await redis.incrby(f"stock:{product_id}", quantity)
           raise InsufficientStockError()
       
       # Create order (database write can be async)
       order = await create_order(...)
       return order
   ```

7. **Your payment sync job runs every 5 minutes, but users want real-time status updates. How do you handle this?**

   *Answer*:
   ```python
   async def get_payment_status(payment_id: int, user_waiting: bool = False):
       payment = await db.get(Payment, payment_id)
       
       if payment.status == "pending":
           if user_waiting:
               # User is actively waiting - sync immediately
               try:
                   external = await stripe_client.get(payment.stripe_id)
                   if external.status != payment.status:
                       payment.status = external.status
                       await db.commit()
               except StripeError:
                   pass  # Return cached if API fails
           else:
               # Check if it's been a while since last sync
               if payment.last_synced_at < datetime.utcnow() - timedelta(seconds=30):
                   # Trigger async sync
                   await background_tasks.add_task(sync_payment, payment_id)
       
       return payment
   
   # Plus: Implement webhooks for instant updates
   @app.post("/webhooks/stripe")
   async def handle_webhook(event: StripeEvent):
       if event.type == "payment_intent.succeeded":
           await update_payment_status(event.data.id, "succeeded")
   ```

8. **You need to sync 10 million records from an external API daily. How do you approach this?**

   *Answer*:
   ```python
   async def daily_full_sync():
       """Incremental sync with checkpointing"""
       checkpoint = await get_last_sync_checkpoint()
       batch_size = 1000
       
       while True:
           # Fetch batch from external API
           records = await external_api.list(
               modified_since=checkpoint.last_modified,
               limit=batch_size,
               offset=checkpoint.offset
           )
           
           if not records:
               break
           
           # Bulk upsert
           await db.execute(
               insert(Record)
               .values([r.dict() for r in records])
               .on_conflict_do_update(...)
           )
           
           # Update checkpoint (for resume on failure)
           checkpoint.offset += len(records)
           if records:
               checkpoint.last_modified = max(r.modified_at for r in records)
           await save_checkpoint(checkpoint)
           
           # Yield control to not block event loop
           await asyncio.sleep(0.1)
       
       # Final checkpoint
       checkpoint.completed_at = datetime.utcnow()
       await save_checkpoint(checkpoint)
   ```

9. **Your cache and database are out of sync after a failed write. How do you handle this?**

   *Answer*:
   ```python
   async def update_with_cache(item_id: int, data: dict):
       try:
           # Update database first
           await db.update(Item, item_id, data)
           
           # Then invalidate cache (not update - safer)
           await cache.delete(f"item:{item_id}")
           
       except DatabaseError:
           # DB write failed - don't touch cache
           raise
       except CacheError:
           # Cache invalidation failed - log and continue
           # Cache will expire eventually, or next read will refresh
           logger.error(f"Failed to invalidate cache for item {item_id}")
           # Option: Queue for retry
           await retry_queue.enqueue("invalidate_cache", f"item:{item_id}")
   
   # For critical consistency:
   async def update_critical(item_id: int, data: dict):
       # Delete cache first (better stale than wrong)
       await cache.delete(f"item:{item_id}")
       
       # Then update database
       await db.update(Item, item_id, data)
       
       # Don't repopulate cache - let next read do it
   ```

10. **Design a system where users can see their order status in real-time, even though order fulfillment involves multiple external services (payment, inventory, shipping).**

    *Answer*:
    ```python
    # Order status aggregator
    async def get_order_status(order_id: int) -> OrderStatus:
        order = await db.get(Order, order_id)
        
        # Aggregate status from all services
        status = OrderStatus(
            order_id=order.id,
            overall_status=order.status,
            steps=[]
        )
        
        # Payment status
        if order.payment_id:
            status.steps.append({
                "name": "payment",
                "status": order.payment_status,
                "updated_at": order.payment_updated_at
            })
        
        # Inventory status
        if order.reservation_id:
            status.steps.append({
                "name": "inventory",
                "status": order.inventory_status,
                "updated_at": order.inventory_updated_at
            })
        
        # Shipping status
        if order.shipment_id:
            # Shipping might need real-time check
            if order.shipping_status == "in_transit":
                try:
                    tracking = await shipping_service.get_tracking(order.shipment_id)
                    status.steps.append({
                        "name": "shipping",
                        "status": tracking.status,
                        "location": tracking.current_location,
                        "updated_at": tracking.updated_at
                    })
                except ShippingAPIError:
                    status.steps.append({
                        "name": "shipping",
                        "status": order.shipping_status,
                        "updated_at": order.shipping_updated_at
                    })
        
        return status
    
    # Event-driven updates
    @event_handler("payment.completed")
    async def on_payment_completed(event):
        await db.execute(
            update(Order)
            .where(Order.id == event.order_id)
            .values(
                payment_status="completed",
                payment_updated_at=datetime.utcnow()
            )
        )
        await notify_user(event.order_id, "Payment successful!")
    ```

---

## Interview Framing

When discussing consistency:

1. **Show trade-off awareness**: "Strong consistency requires more coordination, which hurts latency and availability. I choose consistency level based on business requirements - bank balances need strong consistency, but product view counts can be eventually consistent."

2. **Explain sync strategies**: "I use webhooks for real-time updates when available, with polling as a backup to catch missed events. For high-volume sync, I use incremental syncs with checkpointing to handle failures gracefully."

3. **Discuss race conditions**: "I default to optimistic locking since it scales better. For high-contention resources like inventory, I might use atomic database operations or Redis. I always consider what happens when two requests hit simultaneously."

4. **Connect to user experience**: "Users should see their own changes immediately. I track recent writes and route those users to the primary database. Other users can read from replicas with eventual consistency."

5. **Mention failure handling**: "When cache and database disagree, the database is the source of truth. I invalidate cache on writes rather than updating it - better to have a cache miss than wrong data."
