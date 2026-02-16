# File: backend_fastapi_mastery/04_database_architecture_patterns.md

# Database Architecture Patterns for FastAPI

## Why Architecture Matters

When you first build an API, putting all logic in route handlers feels fast. But as the application grows:
- Route handlers become 200+ lines
- Testing requires hitting actual databases
- Business logic gets duplicated
- Changes break multiple endpoints
- New developers can't understand the code

Good architecture separates concerns, making code testable, maintainable, and understandable.

---

## The Problem: Fat Controllers

Here's what NOT to do (but what most tutorials show):

```python
@app.post("/orders")
async def create_order(
    order: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Validation
    if not current_user.is_active:
        raise HTTPException(403, "Inactive user")
    
    # Check inventory
    product = await db.execute(
        select(Product).where(Product.id == order.product_id)
    )
    product = product.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    
    if product.stock < order.quantity:
        raise HTTPException(400, "Insufficient stock")
    
    # Calculate pricing
    subtotal = product.price * order.quantity
    tax = subtotal * Decimal("0.08")
    total = subtotal + tax
    
    # Apply discount
    if current_user.membership_tier == "gold":
        total *= Decimal("0.9")
    
    # Create order
    db_order = Order(
        user_id=current_user.id,
        product_id=product.id,
        quantity=order.quantity,
        subtotal=subtotal,
        tax=tax,
        total=total,
        status="pending"
    )
    db.add(db_order)
    
    # Update inventory
    product.stock -= order.quantity
    
    # Create payment intent
    payment_intent = await stripe_client.payment_intents.create(
        amount=int(total * 100),
        currency="usd",
        customer=current_user.stripe_customer_id
    )
    
    db_order.payment_intent_id = payment_intent.id
    await db.commit()
    
    # Send confirmation email
    await email_service.send_order_confirmation(
        current_user.email,
        db_order
    )
    
    # Log analytics event
    await analytics.track("order_created", {
        "user_id": current_user.id,
        "order_id": db_order.id,
        "total": float(total)
    })
    
    return db_order
```

**Problems:**
- 60+ lines in a single route
- Impossible to unit test without database + Stripe + email service
- Business logic (pricing, discounts) mixed with infrastructure
- Can't reuse order creation logic elsewhere
- If pricing rules change, you're editing route handlers

---

## Clean Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Routes/Controllers                    │
│              (HTTP concerns, request/response)               │
└─────────────────────────────────┬───────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│                         Services                             │
│              (Business logic, orchestration)                 │
└─────────────────────────────────┬───────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│                       Repositories                           │
│              (Data access, queries)                          │
└─────────────────────────────────┬───────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│                         Database                             │
└─────────────────────────────────────────────────────────────┘
```

**Each layer has one job:**
- **Routes**: HTTP handling, validation, authentication, calling services
- **Services**: Business logic, coordinating operations, enforcing rules
- **Repositories**: Data access abstraction, CRUD operations, queries

---

## The Repository Pattern

### What Is It?

A Repository abstracts data access behind a clean interface. Your service layer doesn't know (or care) if data comes from PostgreSQL, MongoDB, or an in-memory dict.

### Basic Repository

```python
# repositories/user_repository.py
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, user_id: int) -> Optional[User]:
        return await self.session.get(User, user_id)
    
    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def list(
        self,
        *,
        is_active: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[User]:
        query = select(User)
        
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def create(self, **kwargs) -> User:
        user = User(**kwargs)
        self.session.add(user)
        await self.session.flush()  # Get ID without committing
        return user
    
    async def update(self, user: User, **kwargs) -> User:
        for key, value in kwargs.items():
            setattr(user, key, value)
        await self.session.flush()
        return user
    
    async def delete(self, user: User) -> None:
        await self.session.delete(user)
        await self.session.flush()
```

### Generic Base Repository

Avoid duplicating CRUD logic:

```python
# repositories/base.py
from typing import TypeVar, Generic, Optional, List, Type
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.base import Base

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    def __init__(self, session: AsyncSession, model: Type[ModelType]):
        self.session = session
        self.model = model
    
    async def get(self, id: int) -> Optional[ModelType]:
        return await self.session.get(self.model, id)
    
    async def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0
    ) -> List[ModelType]:
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return result.scalars().all()
    
    async def create(self, **kwargs) -> ModelType:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance
    
    async def update(self, instance: ModelType, **kwargs) -> ModelType:
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.flush()
        return instance
    
    async def delete(self, instance: ModelType) -> None:
        await self.session.delete(instance)
        await self.session.flush()

# Specific repository extends base
class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)
    
    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def get_active_users(self) -> List[User]:
        result = await self.session.execute(
            select(User).where(User.is_active == True)
        )
        return result.scalars().all()
```

### Repository as FastAPI Dependency

```python
# dependencies.py
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from repositories.user_repository import UserRepository
from repositories.order_repository import OrderRepository

async def get_user_repository(
    db: AsyncSession = Depends(get_db)
) -> UserRepository:
    return UserRepository(db)

async def get_order_repository(
    db: AsyncSession = Depends(get_db)
) -> OrderRepository:
    return OrderRepository(db)
```

---

## The Service Layer Pattern

### What Is It?

Services contain **business logic**. They orchestrate operations, enforce business rules, and coordinate between repositories and external services.

### Basic Service

```python
# services/user_service.py
from typing import Optional
from repositories.user_repository import UserRepository
from schemas.user import UserCreate, UserUpdate
from models.user import User
from core.security import hash_password, verify_password
from core.exceptions import NotFoundError, ConflictError

class UserService:
    def __init__(self, user_repository: UserRepository):
        self.user_repo = user_repository
    
    async def get_user(self, user_id: int) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User {user_id} not found")
        return user
    
    async def create_user(self, data: UserCreate) -> User:
        # Business rule: email must be unique
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            raise ConflictError(f"Email {data.email} already registered")
        
        # Business logic: hash password
        hashed_password = hash_password(data.password)
        
        # Create user
        user = await self.user_repo.create(
            email=data.email,
            name=data.name,
            hashed_password=hashed_password,
            is_active=True
        )
        
        return user
    
    async def update_user(self, user_id: int, data: UserUpdate) -> User:
        user = await self.get_user(user_id)
        
        update_data = data.model_dump(exclude_unset=True)
        
        # Business rule: can't change email to one that exists
        if "email" in update_data:
            existing = await self.user_repo.get_by_email(update_data["email"])
            if existing and existing.id != user_id:
                raise ConflictError("Email already in use")
        
        return await self.user_repo.update(user, **update_data)
    
    async def authenticate(self, email: str, password: str) -> Optional[User]:
        user = await self.user_repo.get_by_email(email)
        if not user:
            return None
        
        if not verify_password(password, user.hashed_password):
            return None
        
        if not user.is_active:
            return None
        
        return user
```

### Service as FastAPI Dependency

```python
# dependencies.py
async def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository)
) -> UserService:
    return UserService(user_repo)

# routes/users.py
from fastapi import APIRouter, Depends
from services.user_service import UserService
from dependencies import get_user_service

router = APIRouter()

@router.post("/users", status_code=201)
async def create_user(
    data: UserCreate,
    user_service: UserService = Depends(get_user_service)
):
    return await user_service.create_user(data)

@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service)
):
    return await user_service.get_user(user_id)
```

---

## Complex Service Example: Order Service

Now let's refactor that fat controller:

```python
# services/order_service.py
from decimal import Decimal
from typing import Optional
from repositories.order_repository import OrderRepository
from repositories.product_repository import ProductRepository
from repositories.user_repository import UserRepository
from services.payment_service import PaymentService
from services.notification_service import NotificationService
from schemas.order import OrderCreate
from models.order import Order
from core.exceptions import NotFoundError, ValidationError

class OrderService:
    TAX_RATE = Decimal("0.08")
    GOLD_DISCOUNT = Decimal("0.10")
    
    def __init__(
        self,
        order_repo: OrderRepository,
        product_repo: ProductRepository,
        user_repo: UserRepository,
        payment_service: PaymentService,
        notification_service: NotificationService
    ):
        self.order_repo = order_repo
        self.product_repo = product_repo
        self.user_repo = user_repo
        self.payment_service = payment_service
        self.notification_service = notification_service
    
    async def create_order(
        self,
        user_id: int,
        data: OrderCreate
    ) -> Order:
        # Load and validate
        user = await self._get_validated_user(user_id)
        product = await self._get_validated_product(data.product_id)
        
        # Check inventory
        self._validate_inventory(product, data.quantity)
        
        # Calculate pricing
        pricing = self._calculate_pricing(
            product=product,
            quantity=data.quantity,
            user=user
        )
        
        # Create order
        order = await self.order_repo.create(
            user_id=user.id,
            product_id=product.id,
            quantity=data.quantity,
            subtotal=pricing["subtotal"],
            tax=pricing["tax"],
            total=pricing["total"],
            status="pending"
        )
        
        # Reserve inventory
        await self.product_repo.update(
            product,
            stock=product.stock - data.quantity
        )
        
        # Create payment
        payment_intent = await self.payment_service.create_payment_intent(
            amount=pricing["total"],
            customer_id=user.stripe_customer_id
        )
        await self.order_repo.update(
            order,
            payment_intent_id=payment_intent.id
        )
        
        # Send notification (non-blocking)
        await self.notification_service.send_order_confirmation(
            user=user,
            order=order
        )
        
        return order
    
    async def _get_validated_user(self, user_id: int):
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")
        if not user.is_active:
            raise ValidationError("User account is inactive")
        return user
    
    async def _get_validated_product(self, product_id: int):
        product = await self.product_repo.get_by_id(product_id)
        if not product:
            raise NotFoundError("Product not found")
        if not product.is_available:
            raise ValidationError("Product not available")
        return product
    
    def _validate_inventory(self, product, quantity: int):
        if product.stock < quantity:
            raise ValidationError(
                f"Insufficient stock. Available: {product.stock}"
            )
    
    def _calculate_pricing(self, product, quantity: int, user) -> dict:
        subtotal = product.price * quantity
        tax = subtotal * self.TAX_RATE
        total = subtotal + tax
        
        # Apply membership discount
        if user.membership_tier == "gold":
            discount = total * self.GOLD_DISCOUNT
            total -= discount
        
        return {
            "subtotal": subtotal,
            "tax": tax,
            "total": total
        }
```

**Now the route handler is clean:**

```python
@router.post("/orders", status_code=201)
async def create_order(
    data: OrderCreate,
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service)
):
    return await order_service.create_order(
        user_id=current_user.id,
        data=data
    )
```

---

## Why NOT Put Logic in Route Handlers

### 1. Testability

**Fat controller:**
```python
# To test, you need:
# - Real database
# - Real Stripe account
# - Real email service
# - Mock HTTP request

async def test_create_order():
    # 50 lines of setup...
    response = client.post("/orders", json={...})
    assert response.status_code == 201
```

**With service layer:**
```python
# Test business logic in isolation
async def test_create_order():
    # Mock repositories
    user_repo = Mock()
    user_repo.get_by_id.return_value = User(id=1, is_active=True)
    
    product_repo = Mock()
    product_repo.get_by_id.return_value = Product(id=1, stock=10, price=100)
    
    order_repo = Mock()
    payment_service = Mock()
    notification_service = Mock()
    
    service = OrderService(
        order_repo, product_repo, user_repo,
        payment_service, notification_service
    )
    
    order = await service.create_order(user_id=1, data=OrderCreate(...))
    
    assert order_repo.create.called
    assert payment_service.create_payment_intent.called
```

### 2. Reusability

**Fat controller:**
```python
# Need to create order from CLI script?
# Copy-paste 60 lines? Extract to function?

# Need to create order from background task?
# More copy-paste?
```

**With service layer:**
```python
# CLI script
async def main():
    async with get_db_session() as db:
        service = OrderService(...)
        await service.create_order(user_id=1, data=data)

# Background task
async def process_pending_carts():
    async with get_db_session() as db:
        service = OrderService(...)
        for cart in pending_carts:
            await service.create_order(...)
```

### 3. Single Responsibility

Route handlers should only handle HTTP concerns:
- Parsing request
- Validating authentication
- Calling service
- Formatting response
- Setting status code

Services handle business logic:
- Business rules
- Validation rules
- Orchestration
- Error handling

Repositories handle data:
- Queries
- CRUD operations
- Data transformation

### 4. Maintainability

When pricing logic changes:

**Fat controller:** Hunt through all route handlers for pricing code

**Service layer:** Change `_calculate_pricing` in one place

---

## Project Structure

```
app/
├── main.py                 # FastAPI app, router includes
├── database.py             # Engine, session factory
├── dependencies.py         # Dependency injection functions
│
├── models/                 # SQLAlchemy models (ORM)
│   ├── __init__.py
│   ├── base.py
│   ├── user.py
│   ├── order.py
│   └── product.py
│
├── schemas/                # Pydantic models (API)
│   ├── __init__.py
│   ├── user.py
│   ├── order.py
│   └── product.py
│
├── repositories/           # Data access layer
│   ├── __init__.py
│   ├── base.py
│   ├── user_repository.py
│   ├── order_repository.py
│   └── product_repository.py
│
├── services/               # Business logic layer
│   ├── __init__.py
│   ├── user_service.py
│   ├── order_service.py
│   ├── payment_service.py
│   └── notification_service.py
│
├── routes/                 # API routes (controllers)
│   ├── __init__.py
│   ├── users.py
│   ├── orders.py
│   └── products.py
│
├── core/                   # Shared utilities
│   ├── __init__.py
│   ├── config.py           # Settings
│   ├── security.py         # Auth utilities
│   └── exceptions.py       # Custom exceptions
│
└── tests/
    ├── __init__.py
    ├── conftest.py         # Fixtures
    ├── unit/               # Unit tests (services)
    ├── integration/        # Integration tests (repos)
    └── e2e/                # End-to-end tests (routes)
```

---

## Dependency Injection Wiring

```python
# dependencies.py
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from repositories.user_repository import UserRepository
from repositories.order_repository import OrderRepository
from repositories.product_repository import ProductRepository
from services.user_service import UserService
from services.order_service import OrderService
from services.payment_service import PaymentService
from services.notification_service import NotificationService

# Repositories
async def get_user_repository(
    db: AsyncSession = Depends(get_db)
) -> UserRepository:
    return UserRepository(db)

async def get_order_repository(
    db: AsyncSession = Depends(get_db)
) -> OrderRepository:
    return OrderRepository(db)

async def get_product_repository(
    db: AsyncSession = Depends(get_db)
) -> ProductRepository:
    return ProductRepository(db)

# External services
async def get_payment_service() -> PaymentService:
    return PaymentService(api_key=settings.STRIPE_API_KEY)

async def get_notification_service() -> NotificationService:
    return NotificationService(
        email_client=EmailClient(settings.EMAIL_API_KEY)
    )

# Business services (compose dependencies)
async def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository)
) -> UserService:
    return UserService(user_repo)

async def get_order_service(
    order_repo: OrderRepository = Depends(get_order_repository),
    product_repo: ProductRepository = Depends(get_product_repository),
    user_repo: UserRepository = Depends(get_user_repository),
    payment_service: PaymentService = Depends(get_payment_service),
    notification_service: NotificationService = Depends(get_notification_service)
) -> OrderService:
    return OrderService(
        order_repo=order_repo,
        product_repo=product_repo,
        user_repo=user_repo,
        payment_service=payment_service,
        notification_service=notification_service
    )
```

---

## Custom Exceptions

```python
# core/exceptions.py
from fastapi import HTTPException

class AppException(Exception):
    """Base exception for application errors"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

class NotFoundError(AppException):
    """Resource not found"""
    pass

class ConflictError(AppException):
    """Resource conflict (duplicate, etc)"""
    pass

class ValidationError(AppException):
    """Business validation failed"""
    pass

class AuthorizationError(AppException):
    """User not authorized for action"""
    pass

# Exception handlers in main.py
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "NOT_FOUND", "message": exc.message}}
    )

@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError):
    return JSONResponse(
        status_code=409,
        content={"error": {"code": "CONFLICT", "message": exc.message}}
    )

@app.exception_handler(ValidationError)
async def validation_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "VALIDATION_ERROR", "message": exc.message}}
    )
```

---

## Transaction Boundaries

### Where Do Transactions Belong?

Transactions should be managed at the **service layer** or **route layer**, not in repositories.

```python
# WRONG: Transaction per repository method
class UserRepository:
    async def create(self, **kwargs):
        user = User(**kwargs)
        self.session.add(user)
        await self.session.commit()  # Commits immediately!
        return user

# Problem: What if service needs to create user AND order atomically?

# RIGHT: Repository only flushes, service/route commits
class UserRepository:
    async def create(self, **kwargs):
        user = User(**kwargs)
        self.session.add(user)
        await self.session.flush()  # Gets ID, doesn't commit
        return user

# Service orchestrates, route commits
@router.post("/register")
async def register(
    data: RegisterRequest,
    user_service: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db)
):
    # Service does work, repositories flush
    user = await user_service.create_user(data.user)
    profile = await user_service.create_profile(user.id, data.profile)
    
    # Route commits the transaction
    # (or let the dependency do it on success)
    return {"user": user, "profile": profile}
```

### Unit of Work Pattern

For complex transactions:

```python
# services/registration_service.py
class RegistrationService:
    def __init__(
        self,
        user_repo: UserRepository,
        profile_repo: ProfileRepository,
        email_service: EmailService
    ):
        self.user_repo = user_repo
        self.profile_repo = profile_repo
        self.email_service = email_service
    
    async def register_user(self, data: RegistrationData) -> User:
        """
        Creates user and profile in single transaction.
        Either both succeed or both fail.
        """
        # Check uniqueness
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            raise ConflictError("Email already registered")
        
        # Create user (flush, not commit)
        user = await self.user_repo.create(
            email=data.email,
            hashed_password=hash_password(data.password)
        )
        
        # Create profile (same transaction)
        profile = await self.profile_repo.create(
            user_id=user.id,  # ID available from flush
            name=data.name,
            bio=data.bio
        )
        
        # Both created, transaction will commit when route/dependency does
        
        # Queue email (outside transaction)
        await self.email_service.queue_welcome_email(user.email)
        
        return user
```

---

## Anti-Patterns to Avoid

### 1. Anemic Domain Model

```python
# WRONG: Models are just data bags, logic scattered everywhere
class User(Base):
    id = Column(Integer, primary_key=True)
    email = Column(String)
    password_hash = Column(String)
    is_active = Column(Boolean)
    # No methods

# Logic duplicated in services
if user.is_active and user.email_verified:
    ...

# BETTER: Add meaningful methods to models
class User(Base):
    # ... columns ...
    
    @property
    def can_login(self) -> bool:
        return self.is_active and self.email_verified
    
    def verify_password(self, password: str) -> bool:
        return verify_hash(password, self.password_hash)
```

### 2. Circular Dependencies

```python
# WRONG: Services depend on each other
class UserService:
    def __init__(self, order_service: OrderService):
        self.order_service = order_service

class OrderService:
    def __init__(self, user_service: UserService):  # Circular!
        self.user_service = user_service

# RIGHT: Use shared dependencies or events
class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

class OrderService:
    def __init__(self, order_repo: OrderRepository, user_repo: UserRepository):
        self.order_repo = order_repo
        self.user_repo = user_repo  # Use repo directly
```

### 3. Leaky Abstractions

```python
# WRONG: Repository exposes SQLAlchemy details
class UserRepository:
    def get_query(self):
        return select(User)  # Service now depends on SQLAlchemy

# Service
users = await user_repo.get_query().where(User.is_active == True).all()

# RIGHT: Repository provides complete operations
class UserRepository:
    async def get_active_users(self, limit: int = 100) -> List[User]:
        result = await self.session.execute(
            select(User).where(User.is_active == True).limit(limit)
        )
        return result.scalars().all()
```

### 4. Over-Engineering

```python
# WRONG: Abstract factory factory pattern for a simple CRUD app
class AbstractRepositoryFactory(ABC):
    @abstractmethod
    def create_user_repository(self) -> AbstractUserRepository:
        pass

class PostgresRepositoryFactory(AbstractRepositoryFactory):
    def create_user_repository(self) -> PostgresUserRepository:
        return PostgresUserRepository(self.engine)

# RIGHT: Start simple, add abstraction when needed
class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
```

---

## Mastery Checkpoints

### Conceptual Questions

1. **What's the difference between a Repository and a Service?**

   *Answer*: A Repository handles data access - CRUD operations, queries, talking to the database. It doesn't contain business logic. A Service handles business logic - validation rules, calculations, orchestrating multiple repositories. The repository answers "how do I get this data?" The service answers "what are the business rules?"

2. **Why shouldn't you call `session.commit()` inside a repository?**

   *Answer*: Because it prevents the service layer from orchestrating transactions. If repo A commits and repo B fails, you have partial data. The repository should `flush()` to get IDs and check constraints, but the transaction boundary should be controlled by the caller (service or route) so multiple operations can be atomic.

3. **When would you add a method to the model vs the service?**

   *Answer*: Add to model if it's intrinsic to the entity - `user.can_login`, `order.is_cancellable`, `product.discounted_price`. Add to service if it involves other entities, external services, or complex orchestration - `user_service.create_user()`, `order_service.process_refund()`.

4. **How does the repository pattern help with testing?**

   *Answer*: You can mock the repository interface in service tests without touching the database. Test `UserService.create_user()` by injecting a mock `UserRepository` that returns test data. You only need real database tests for repository methods themselves.

5. **What's the problem with "fat controllers"?**

   *Answer*: Can't unit test (need full HTTP stack + database), can't reuse logic, hard to maintain as code grows, mixes concerns (HTTP handling + business logic + data access), violates single responsibility principle.

### Scenario Questions

6. **Design the service layer for a ride-sharing app with riders, drivers, and trips.**

   *Answer*:
   ```python
   class TripService:
       def __init__(
           self,
           trip_repo: TripRepository,
           rider_repo: RiderRepository,
           driver_repo: DriverRepository,
           pricing_service: PricingService,
           notification_service: NotificationService,
           location_service: LocationService
       ):
           ...
       
       async def request_trip(self, rider_id: int, pickup: Location, dropoff: Location):
           rider = await self.rider_repo.get(rider_id)
           self._validate_rider_can_request(rider)
           
           price = await self.pricing_service.calculate_fare(pickup, dropoff)
           
           trip = await self.trip_repo.create(
               rider_id=rider_id,
               pickup=pickup,
               dropoff=dropoff,
               estimated_fare=price,
               status="requested"
           )
           
           await self._find_and_notify_drivers(trip)
           return trip
       
       async def accept_trip(self, trip_id: int, driver_id: int):
           trip = await self.trip_repo.get(trip_id)
           driver = await self.driver_repo.get(driver_id)
           
           self._validate_trip_acceptable(trip)
           self._validate_driver_available(driver)
           
           await self.trip_repo.update(trip, driver_id=driver_id, status="accepted")
           await self.driver_repo.update(driver, status="busy")
           await self.notification_service.notify_rider(trip.rider_id, "Driver found!")
           
           return trip
   ```

7. **You need to implement a checkout process that: validates cart, reserves inventory, charges payment, creates order, sends confirmation. How do you structure it?**

   *Answer*:
   ```python
   class CheckoutService:
       async def checkout(self, user_id: int, cart_id: int) -> Order:
           # Load and validate
           cart = await self.cart_repo.get_with_items(cart_id)
           self._validate_cart(cart)
           
           # Reserve inventory (transaction will rollback if later steps fail)
           await self._reserve_inventory(cart.items)
           
           # Calculate totals
           totals = self._calculate_totals(cart)
           
           # Create order (pending status)
           order = await self.order_repo.create(
               user_id=user_id,
               items=cart.items,
               total=totals.total,
               status="pending_payment"
           )
           
           try:
               # Charge payment
               payment = await self.payment_service.charge(
                   amount=totals.total,
                   customer_id=user.payment_customer_id,
                   idempotency_key=f"order_{order.id}"
               )
               
               await self.order_repo.update(order, 
                   payment_id=payment.id,
                   status="paid"
               )
           except PaymentError as e:
               # Release inventory, update order status
               await self._release_inventory(cart.items)
               await self.order_repo.update(order, status="payment_failed")
               raise CheckoutError("Payment failed")
           
           # Clear cart, send confirmation (non-critical)
           await self.cart_repo.clear(cart_id)
           await self.notification_service.send_order_confirmation(order)
           
           return order
   ```

8. **How do you handle the case where you need to call an external API and update the database atomically?**

   *Answer*: You can't have true atomicity across database and external API. Use compensating transactions:
   ```python
   async def create_subscription(self, user_id: int, plan_id: int):
       # 1. Create subscription in our DB (pending)
       sub = await self.sub_repo.create(
           user_id=user_id,
           plan_id=plan_id,
           status="pending"
       )
       
       try:
           # 2. Create in Stripe
           stripe_sub = await self.stripe_service.create_subscription(
               customer_id=user.stripe_id,
               price_id=plan.stripe_price_id,
               idempotency_key=f"sub_{sub.id}"
           )
           
           # 3. Update our record
           await self.sub_repo.update(sub,
               stripe_subscription_id=stripe_sub.id,
               status="active"
           )
       except StripeError:
           # Compensate: mark our record as failed
           await self.sub_repo.update(sub, status="failed")
           raise
       
       return sub
   ```

9. **Your service needs data from two repositories. One is fast (Redis cache), one is slow (PostgreSQL). How do you structure this?**

   *Answer*:
   ```python
   class ProductService:
       def __init__(
           self,
           product_repo: ProductRepository,  # PostgreSQL
           cache_repo: ProductCacheRepository  # Redis
       ):
           ...
       
       async def get_product(self, product_id: int):
           # Try cache first
           cached = await self.cache_repo.get(product_id)
           if cached:
               return cached
           
           # Fall back to database
           product = await self.product_repo.get(product_id)
           if product:
               await self.cache_repo.set(product_id, product, ttl=300)
           
           return product
   ```

10. **How do you test a service that depends on an external payment API?**

    *Answer*:
    ```python
    # Create interface for payment service
    class PaymentServiceProtocol(Protocol):
        async def charge(self, amount: int, customer_id: str) -> PaymentResult:
            ...
    
    # Real implementation
    class StripePaymentService:
        async def charge(self, amount: int, customer_id: str) -> PaymentResult:
            # Actually call Stripe
            ...
    
    # Test mock
    class MockPaymentService:
        def __init__(self, should_fail: bool = False):
            self.should_fail = should_fail
            self.charges = []
        
        async def charge(self, amount: int, customer_id: str) -> PaymentResult:
            self.charges.append((amount, customer_id))
            if self.should_fail:
                raise PaymentError("Card declined")
            return PaymentResult(id="test_123", status="succeeded")
    
    # In tests
    async def test_checkout_success():
        mock_payment = MockPaymentService()
        service = CheckoutService(payment_service=mock_payment, ...)
        
        order = await service.checkout(user_id=1, cart_id=1)
        
        assert len(mock_payment.charges) == 1
        assert order.status == "paid"
    
    async def test_checkout_payment_failure():
        mock_payment = MockPaymentService(should_fail=True)
        service = CheckoutService(payment_service=mock_payment, ...)
        
        with pytest.raises(CheckoutError):
            await service.checkout(user_id=1, cart_id=1)
    ```

---

## Interview Framing

When discussing architecture in interviews:

1. **Explain the why**: "I separate concerns because it makes the codebase testable and maintainable. I can unit test business logic without spinning up a database or mocking HTTP requests."

2. **Show pragmatism**: "I don't always need all layers. For a simple CRUD endpoint, a thin service that delegates to a repository is fine. I add complexity when the business logic demands it."

3. **Discuss trade-offs**: "Repository pattern adds indirection, which is overhead for simple queries. But it pays off when I need to swap databases, add caching, or test services in isolation."

4. **Connect to testing**: "With this structure, I test services with mocked repositories (fast, isolated), repositories with test databases (verify queries), and routes with TestClient (integration)."

5. **Mention real experience**: "In production, this separation helped when we needed to add Redis caching. We added a cache layer in the repository without touching any service code."
