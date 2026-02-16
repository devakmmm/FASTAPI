# File: backend_fastapi_mastery/12_testing_strategies.md

# Testing Strategies for FastAPI

## The Testing Pyramid

```
         /\
        /  \        E2E Tests (few)
       /----\       - Full system integration
      /      \      - Slow, expensive, flaky
     /--------\     
    /          \    Integration Tests (some)
   /------------\   - Service + database
  /              \  - External APIs mocked
 /----------------\ 
/                  \ Unit Tests (many)
                    - Business logic
                    - Fast, isolated
```

---

## Unit Testing FastAPI

### Testing Service Layer

```python
# services/order_service.py
class OrderService:
    def __init__(self, order_repo: OrderRepository, payment_service: PaymentService):
        self.order_repo = order_repo
        self.payment_service = payment_service
    
    async def create_order(self, user_id: int, items: list) -> Order:
        total = sum(item.price * item.quantity for item in items)
        
        if total <= 0:
            raise ValidationError("Order total must be positive")
        
        order = await self.order_repo.create(
            user_id=user_id,
            items=items,
            total=total,
            status="pending"
        )
        
        return order

# tests/unit/test_order_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from services.order_service import OrderService
from core.exceptions import ValidationError

@pytest.fixture
def mock_order_repo():
    repo = AsyncMock()
    repo.create.return_value = Order(id=1, status="pending", total=100)
    return repo

@pytest.fixture
def mock_payment_service():
    return AsyncMock()

@pytest.fixture
def order_service(mock_order_repo, mock_payment_service):
    return OrderService(mock_order_repo, mock_payment_service)

class TestOrderService:
    @pytest.mark.asyncio
    async def test_create_order_success(self, order_service, mock_order_repo):
        items = [MagicMock(price=50, quantity=2)]
        
        result = await order_service.create_order(user_id=1, items=items)
        
        assert result.id == 1
        mock_order_repo.create.assert_called_once()
        call_args = mock_order_repo.create.call_args
        assert call_args.kwargs["total"] == 100
    
    @pytest.mark.asyncio
    async def test_create_order_zero_total_raises(self, order_service):
        items = [MagicMock(price=0, quantity=1)]
        
        with pytest.raises(ValidationError) as exc_info:
            await order_service.create_order(user_id=1, items=items)
        
        assert "positive" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_order_calculates_total_correctly(self, order_service, mock_order_repo):
        items = [
            MagicMock(price=10, quantity=3),  # 30
            MagicMock(price=20, quantity=2),  # 40
        ]
        
        await order_service.create_order(user_id=1, items=items)
        
        call_args = mock_order_repo.create.call_args
        assert call_args.kwargs["total"] == 70
```

### Testing Pydantic Models

```python
# tests/unit/test_schemas.py
import pytest
from pydantic import ValidationError
from schemas.user import UserCreate

class TestUserCreate:
    def test_valid_user(self):
        user = UserCreate(
            email="test@example.com",
            password="SecurePass123!",
            name="John Doe"
        )
        assert user.email == "test@example.com"
    
    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                email="not-an-email",
                password="SecurePass123!",
                name="John"
            )
        
        assert "email" in str(exc_info.value)
    
    def test_password_too_short_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(
                email="test@example.com",
                password="short",
                name="John"
            )
    
    def test_email_normalized_to_lowercase(self):
        user = UserCreate(
            email="TEST@EXAMPLE.COM",
            password="SecurePass123!",
            name="John"
        )
        assert user.email == "test@example.com"
```

---

## Integration Testing with TestClient

### Basic Route Testing

```python
# tests/integration/test_users.py
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from main import app

# Synchronous client for simple tests
client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_create_user():
    response = client.post("/users", json={
        "email": "test@example.com",
        "password": "SecurePass123!",
        "name": "Test User"
    })
    assert response.status_code == 201
    assert response.json()["email"] == "test@example.com"
    assert "password" not in response.json()  # Not exposed

def test_create_user_duplicate_email():
    # First user
    client.post("/users", json={
        "email": "duplicate@example.com",
        "password": "SecurePass123!",
        "name": "First"
    })
    
    # Duplicate
    response = client.post("/users", json={
        "email": "duplicate@example.com",
        "password": "SecurePass123!",
        "name": "Second"
    })
    
    assert response.status_code == 409
```

### Async Testing with pytest-asyncio

```python
# tests/integration/test_async_routes.py
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_async_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/async-data")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_concurrent_requests():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Test concurrent request handling
        responses = await asyncio.gather(
            client.get("/users/1"),
            client.get("/users/2"),
            client.get("/users/3"),
        )
        
        for response in responses:
            assert response.status_code in [200, 404]
```

---

## Database Testing

### Test Database Setup

```python
# tests/conftest.py
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from models.base import Base
from database import get_db
from main import app

# Use separate test database
TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost/test_db"

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()

@pytest.fixture
async def db_session(test_engine):
    """Create new session for each test, rollback after"""
    async_session = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()

@pytest.fixture
async def client(db_session):
    """Test client with overridden database"""
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()
```

### Database Test Examples

```python
# tests/integration/test_orders_db.py
import pytest
from models.order import Order
from models.user import User

@pytest.fixture
async def test_user(db_session):
    user = User(email="test@test.com", name="Test", hashed_password="hash")
    db_session.add(user)
    await db_session.flush()
    return user

@pytest.mark.asyncio
async def test_create_order(client, test_user):
    response = await client.post(
        "/orders",
        json={"product_id": 1, "quantity": 2},
        headers={"Authorization": f"Bearer {create_token(test_user.id)}"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == test_user.id

@pytest.mark.asyncio
async def test_user_can_only_see_own_orders(client, db_session, test_user):
    # Create another user's order
    other_user = User(email="other@test.com", name="Other", hashed_password="hash")
    db_session.add(other_user)
    await db_session.flush()
    
    other_order = Order(user_id=other_user.id, total=100)
    db_session.add(other_order)
    await db_session.flush()
    
    # Try to access other user's order
    response = await client.get(
        f"/orders/{other_order.id}",
        headers={"Authorization": f"Bearer {create_token(test_user.id)}"}
    )
    
    assert response.status_code == 403
```

---

## Dependency Overrides

### Mocking Authentication

```python
# tests/conftest.py
from dependencies import get_current_user
from models.user import User

@pytest.fixture
def mock_user():
    return User(
        id=1,
        email="test@test.com",
        name="Test User",
        is_active=True,
        is_admin=False
    )

@pytest.fixture
def authenticated_client(client, mock_user):
    async def override_get_current_user():
        return mock_user
    
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield client
    app.dependency_overrides.clear()

@pytest.fixture
def admin_client(client):
    admin_user = User(
        id=1,
        email="admin@test.com",
        name="Admin",
        is_active=True,
        is_admin=True
    )
    
    async def override():
        return admin_user
    
    app.dependency_overrides[get_current_user] = override
    yield client
    app.dependency_overrides.clear()
```

### Mocking External Services

```python
# tests/conftest.py
from services.payment_service import PaymentService
from dependencies import get_payment_service

@pytest.fixture
def mock_payment_service():
    service = AsyncMock(spec=PaymentService)
    service.create_charge.return_value = {
        "id": "ch_test123",
        "status": "succeeded"
    }
    return service

@pytest.fixture
def client_with_mock_payment(client, mock_payment_service):
    async def override():
        return mock_payment_service
    
    app.dependency_overrides[get_payment_service] = override
    yield client
    app.dependency_overrides.clear()

# Usage in tests
@pytest.mark.asyncio
async def test_checkout_charges_payment(client_with_mock_payment, mock_payment_service):
    response = await client_with_mock_payment.post("/checkout", json={...})
    
    assert response.status_code == 200
    mock_payment_service.create_charge.assert_called_once()
```

---

## Mocking External APIs

### Using responses Library

```python
import responses
import httpx

@responses.activate
def test_external_api_call():
    # Mock the external API
    responses.add(
        responses.GET,
        "https://api.example.com/data",
        json={"result": "mocked"},
        status=200
    )
    
    # Your code calls the external API
    result = fetch_external_data()
    
    assert result == {"result": "mocked"}
```

### Using respx for Async

```python
import respx
import httpx

@pytest.mark.asyncio
@respx.mock
async def test_async_external_api():
    # Mock the external API
    respx.get("https://api.example.com/data").respond(
        json={"result": "mocked"}
    )
    
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")
        assert response.json() == {"result": "mocked"}

@pytest.mark.asyncio
@respx.mock
async def test_external_api_error_handling():
    # Mock a failure
    respx.get("https://api.example.com/data").respond(status_code=500)
    
    with pytest.raises(ExternalServiceError):
        await fetch_external_data()

@pytest.mark.asyncio
@respx.mock
async def test_external_api_timeout():
    # Mock a timeout
    respx.get("https://api.example.com/data").mock(
        side_effect=httpx.TimeoutException("Timeout")
    )
    
    with pytest.raises(TimeoutError):
        await fetch_external_data()
```

---

## Testing Patterns

### Factories for Test Data

```python
# tests/factories.py
from models.user import User
from models.order import Order
import factory
from factory.alchemy import SQLAlchemyModelFactory

class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session_persistence = "commit"
    
    email = factory.Sequence(lambda n: f"user{n}@test.com")
    name = factory.Faker("name")
    hashed_password = "hashed_password"
    is_active = True
    is_admin = False

class OrderFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Order
    
    user = factory.SubFactory(UserFactory)
    total = factory.Faker("pydecimal", left_digits=3, right_digits=2, positive=True)
    status = "pending"

# Usage
def test_with_factories(db_session):
    user = UserFactory(is_admin=True)
    orders = OrderFactory.create_batch(5, user=user)
    
    assert len(orders) == 5
    assert all(o.user_id == user.id for o in orders)
```

### Parameterized Tests

```python
import pytest

@pytest.mark.parametrize("status_code,expected_message", [
    (200, "success"),
    (400, "bad request"),
    (401, "unauthorized"),
    (403, "forbidden"),
    (404, "not found"),
    (500, "internal error"),
])
def test_error_responses(client, status_code, expected_message):
    response = client.get(f"/test-errors/{status_code}")
    assert response.status_code == status_code
    assert expected_message in response.json()["message"].lower()

@pytest.mark.parametrize("input_data,expected_error", [
    ({"email": "invalid"}, "email"),
    ({"email": "test@test.com", "password": "short"}, "password"),
    ({"email": "test@test.com", "password": "ValidPass123!", "name": ""}, "name"),
])
def test_validation_errors(client, input_data, expected_error):
    response = client.post("/users", json=input_data)
    assert response.status_code == 422
    assert expected_error in str(response.json())
```

### Testing Webhooks

```python
@pytest.mark.asyncio
async def test_stripe_webhook(client):
    # Create webhook payload
    payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_test123",
                "amount": 1000
            }
        }
    }
    
    # Create signature (Stripe signs webhooks)
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{json.dumps(payload)}"
    signature = hmac.new(
        WEBHOOK_SECRET.encode(),
        signed_payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    response = await client.post(
        "/webhooks/stripe",
        json=payload,
        headers={
            "Stripe-Signature": f"t={timestamp},v1={signature}"
        }
    )
    
    assert response.status_code == 200
```

---

## Test Configuration

### pytest.ini

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short --strict-markers
markers =
    slow: marks tests as slow
    integration: marks tests as integration tests
    e2e: marks tests as end-to-end tests
filterwarnings =
    ignore::DeprecationWarning
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run only unit tests
pytest tests/unit

# Run only fast tests (exclude slow)
pytest -m "not slow"

# Run specific test file
pytest tests/integration/test_orders.py

# Run specific test
pytest tests/integration/test_orders.py::test_create_order

# Run with verbose output
pytest -v

# Run and stop on first failure
pytest -x
```

---

## Mastery Checkpoints

### Conceptual Questions

1. **Why use dependency overrides instead of mocking directly?**

   *Answer*: Dependency overrides work with FastAPI's DI system, replacing dependencies cleanly at the container level. Direct mocking might miss how dependencies are resolved or create coupling to implementation details. Overrides test the actual DI wiring while controlling what's injected.

2. **What's the difference between TestClient and AsyncClient?**

   *Answer*: TestClient is synchronous - it runs ASGI app in a thread, suitable for simple tests. AsyncClient (httpx) is async - it works with pytest-asyncio for testing async endpoints properly. Use AsyncClient when testing async behavior, concurrent requests, or async fixtures.

3. **Why rollback database transactions in tests?**

   *Answer*: Isolation - each test starts with a clean state. Without rollback, test order matters, tests affect each other, and debugging becomes hard. Rollback is also faster than recreating tables for each test.

4. **When should you mock vs use real implementations?**

   *Answer*: Mock external services (Stripe, email), slow operations, and things that cause side effects. Use real implementations for your code's logic, database (with test DB), and anything that's the subject of the test. The test pyramid guides this: more mocking at unit level, less at integration level.

5. **How do you test that authentication is required?**

   *Answer*: Test both authenticated and unauthenticated requests. For protected endpoints, verify 401 without token, 403 with invalid permissions, and success with valid auth. Use dependency overrides to control auth state in tests.

### Scenario Questions

6. **Design tests for an endpoint that creates orders, charges payments, and sends confirmation emails.**

   *Answer*:
   ```python
   @pytest.fixture
   def mock_payment():
       service = AsyncMock()
       service.charge.return_value = {"id": "ch_123", "status": "succeeded"}
       return service
   
   @pytest.fixture
   def mock_email():
       return AsyncMock()
   
   @pytest.mark.asyncio
   async def test_create_order_success(client, mock_payment, mock_email):
       # Override dependencies
       app.dependency_overrides[get_payment_service] = lambda: mock_payment
       app.dependency_overrides[get_email_service] = lambda: mock_email
       
       response = await client.post("/orders", json={"items": [...]})
       
       assert response.status_code == 201
       mock_payment.charge.assert_called_once()
       mock_email.send.assert_called_once()
   
   @pytest.mark.asyncio
   async def test_create_order_payment_failure(client, mock_payment, mock_email):
       mock_payment.charge.side_effect = PaymentError("Card declined")
       
       response = await client.post("/orders", json={"items": [...]})
       
       assert response.status_code == 400
       assert "payment" in response.json()["error"].lower()
       mock_email.send.assert_not_called()  # No email on failure
   ```

7. **How do you test rate limiting?**

   *Answer*:
   ```python
   @pytest.mark.asyncio
   async def test_rate_limiting(client):
       # Make requests up to limit
       for i in range(60):
           response = await client.get("/api/data")
           assert response.status_code == 200
       
       # Next request should be rate limited
       response = await client.get("/api/data")
       assert response.status_code == 429
       assert "Retry-After" in response.headers
   
   @pytest.mark.asyncio
   async def test_rate_limit_resets(client, mock_redis):
       # Set up rate limit to reset
       mock_redis.get.return_value = None  # Fresh state
       
       response = await client.get("/api/data")
       assert response.status_code == 200
   ```

8. **How do you test background tasks?**

   *Answer*:
   ```python
   @pytest.mark.asyncio
   async def test_background_task_triggered(client):
       with patch("app.routes.send_email_async") as mock_task:
           response = await client.post("/users", json={...})
           
           assert response.status_code == 201
           # Background task was scheduled
           mock_task.assert_called_once()
   
   # For Celery tasks
   @pytest.mark.asyncio
   async def test_celery_task(client, celery_worker):
       response = await client.post("/reports", json={...})
       
       task_id = response.json()["task_id"]
       result = AsyncResult(task_id)
       
       # Wait for completion
       result.get(timeout=10)
       
       assert result.status == "SUCCESS"
   ```

9. **How do you test database migrations?**

   *Answer*:
   ```python
   def test_migrations_up_down():
       """Test all migrations can be applied and rolled back"""
       alembic_config = Config("alembic.ini")
       
       # Start from base
       command.downgrade(alembic_config, "base")
       
       # Apply all migrations
       command.upgrade(alembic_config, "head")
       
       # Rollback all
       command.downgrade(alembic_config, "base")
       
       # Apply again (tests idempotency)
       command.upgrade(alembic_config, "head")
   
   def test_data_migration():
       """Test specific data migration"""
       # Apply up to previous migration
       command.upgrade(alembic_config, "abc123")
       
       # Insert test data in old format
       with engine.connect() as conn:
           conn.execute("INSERT INTO users (name) VALUES ('John Doe')")
       
       # Apply the migration
       command.upgrade(alembic_config, "def456")
       
       # Verify data transformed correctly
       with engine.connect() as conn:
           result = conn.execute("SELECT first_name, last_name FROM users")
           row = result.fetchone()
           assert row.first_name == "John"
           assert row.last_name == "Doe"
   ```

10. **How do you test concurrent access and race conditions?**

    *Answer*:
    ```python
    @pytest.mark.asyncio
    async def test_concurrent_inventory_update(client, db_session):
        # Create product with limited stock
        product = Product(id=1, stock=5)
        db_session.add(product)
        await db_session.commit()
        
        # Simulate 10 concurrent purchases of quantity 1
        async def purchase():
            return await client.post(
                f"/products/1/purchase",
                json={"quantity": 1}
            )
        
        responses = await asyncio.gather(
            *[purchase() for _ in range(10)]
        )
        
        # Only 5 should succeed (stock was 5)
        success_count = sum(1 for r in responses if r.status_code == 200)
        assert success_count == 5
        
        # Verify stock is 0
        await db_session.refresh(product)
        assert product.stock == 0
    ```

---

## Interview Framing

When discussing testing:

1. **Show testing strategy**: "I follow the testing pyramid - many fast unit tests for business logic, fewer integration tests for database and API endpoints, and minimal E2E tests for critical paths. This gives fast feedback while ensuring system integrity."

2. **Explain mock usage**: "I mock external services to keep tests fast and deterministic. But I use real databases (test instances) because the ORM interaction is critical to test. I can override any dependency in FastAPI cleanly."

3. **Discuss test organization**: "I separate unit and integration tests. Unit tests are pure Python, no I/O. Integration tests use TestClient with a real database, dependencies overridden. This makes it easy to run quick checks vs full validation."

4. **Mention CI/CD integration**: "Tests run on every PR. Fast unit tests gate the PR, integration tests run in parallel. Coverage is tracked but not strictly enforced - I focus on testing critical paths and edge cases."

5. **Connect to reliability**: "Good tests let me deploy with confidence. I've caught numerous bugs in code review because tests failed. Refactoring is safe because tests verify behavior didn't change."
