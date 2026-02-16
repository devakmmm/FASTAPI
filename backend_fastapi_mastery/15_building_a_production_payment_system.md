# File: backend_fastapi_mastery/15_building_a_production_payment_system.md

# Building a Production Payment System

## Capstone Project Overview

This module ties together everything you've learned by building a production-grade payment tracking system. You'll see how the patterns from previous modules combine into a real application.

### System Requirements

We're building a system that:
1. Creates payment intents via Stripe
2. Tracks payment status locally
3. Syncs with Stripe via webhooks and polling
4. Provides a status API for clients
5. Handles failures gracefully

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                           Client                                      │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                          FastAPI App                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │   Routes        │  │   Services      │  │   Repositories      │  │
│  │  /payments      │─▶│ PaymentService  │─▶│ PaymentRepository   │  │
│  │  /webhooks      │  │ StripeClient    │  │                     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │
└───────────────┬───────────────┬───────────────────┬─────────────────┘
                │               │                   │
                ▼               ▼                   ▼
         ┌──────────┐   ┌──────────────┐    ┌──────────────┐
         │  Redis   │   │   Stripe     │    │  PostgreSQL  │
         │ (Cache)  │   │    API       │    │  (Storage)   │
         └──────────┘   └──────────────┘    └──────────────┘
```

---

## Database Schema

```python
# models/payment.py
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from decimal import Decimal
import enum

class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"

class Payment(Base):
    __tablename__ = "payments"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Business identifiers
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    order_id: Mapped[int] = mapped_column(index=True)
    
    # Amount
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="usd")
    
    # Status tracking
    status: Mapped[PaymentStatus] = mapped_column(default=PaymentStatus.PENDING)
    
    # Stripe references
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Error tracking
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    
    # Audit
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    
    __table_args__ = (
        Index("ix_payments_status_created", "status", "created_at"),
    )
```

```python
# Alembic migration
def upgrade():
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('idempotency_key', sa.String(64), unique=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), default='usd'),
        sa.Column('status', sa.Enum(PaymentStatus), default='pending'),
        sa.Column('stripe_payment_intent_id', sa.String(100), unique=True, nullable=True),
        sa.Column('stripe_customer_id', sa.String(100), nullable=True),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('error_message', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('metadata', sa.JSON(), default=dict),
    )
    op.create_index('ix_payments_user_id', 'payments', ['user_id'])
    op.create_index('ix_payments_order_id', 'payments', ['order_id'])
    op.create_index('ix_payments_idempotency_key', 'payments', ['idempotency_key'])
    op.create_index('ix_payments_status_created', 'payments', ['status', 'created_at'])
```

---

## Pydantic Schemas

```python
# schemas/payment.py
from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import datetime
from typing import Optional

class PaymentCreate(BaseModel):
    order_id: int
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    currency: str = Field(default="usd", pattern="^[a-z]{3}$")
    idempotency_key: str = Field(..., min_length=16, max_length=64)
    metadata: dict = Field(default_factory=dict)

class PaymentResponse(BaseModel):
    id: int
    idempotency_key: str
    order_id: int
    amount: Decimal
    currency: str
    status: str
    stripe_payment_intent_id: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    processed_at: Optional[datetime]
    
    model_config = {"from_attributes": True}

class PaymentStatusResponse(BaseModel):
    payment_id: int
    status: str
    is_terminal: bool  # True if no more changes expected
    error_message: Optional[str]
    last_synced_at: Optional[datetime]
```

---

## Repository Layer

```python
# repositories/payment_repository.py
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from models.payment import Payment, PaymentStatus

class PaymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, payment_id: int) -> Optional[Payment]:
        return await self.session.get(Payment, payment_id)
    
    async def get_by_idempotency_key(self, key: str) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.idempotency_key == key)
        )
        return result.scalar_one_or_none()
    
    async def get_by_stripe_intent_id(self, intent_id: str) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.stripe_payment_intent_id == intent_id)
        )
        return result.scalar_one_or_none()
    
    async def get_pending_payments(
        self,
        older_than_minutes: int = 5,
        limit: int = 100
    ) -> List[Payment]:
        """Get pending payments that might need syncing"""
        cutoff = datetime.utcnow() - timedelta(minutes=older_than_minutes)
        result = await self.session.execute(
            select(Payment)
            .where(Payment.status == PaymentStatus.PENDING)
            .where(Payment.created_at < cutoff)
            .order_by(Payment.created_at)
            .limit(limit)
        )
        return result.scalars().all()
    
    async def create(self, **kwargs) -> Payment:
        payment = Payment(**kwargs)
        self.session.add(payment)
        await self.session.flush()
        return payment
    
    async def update_status(
        self,
        payment: Payment,
        status: PaymentStatus,
        **kwargs
    ) -> Payment:
        payment.status = status
        payment.updated_at = datetime.utcnow()
        
        for key, value in kwargs.items():
            setattr(payment, key, value)
        
        await self.session.flush()
        return payment
```

---

## Stripe Client

```python
# clients/stripe_client.py
import httpx
from typing import Optional
from decimal import Decimal
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
from core.exceptions import ExternalServiceError
import logging

logger = logging.getLogger(__name__)

class StripeClient:
    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient,
        circuit_breaker: CircuitBreaker
    ):
        self.api_key = api_key
        self.client = http_client
        self.circuit = circuit_breaker
        self.base_url = "https://api.stripe.com/v1"
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        
        async def make_request():
            response = await self.client.request(
                method,
                f"{self.base_url}{endpoint}",
                headers=headers,
                **kwargs
            )
            
            if response.status_code >= 500:
                raise ExternalServiceError(f"Stripe error: {response.status_code}")
            
            response.raise_for_status()
            return response.json()
        
        return await self.circuit.call(make_request)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10)
    )
    async def create_payment_intent(
        self,
        amount_cents: int,
        currency: str,
        customer_id: Optional[str],
        idempotency_key: str,
        metadata: dict = None
    ) -> dict:
        """Create a Stripe PaymentIntent"""
        data = {
            "amount": amount_cents,
            "currency": currency,
            "automatic_payment_methods[enabled]": "true",
        }
        
        if customer_id:
            data["customer"] = customer_id
        
        if metadata:
            for key, value in metadata.items():
                data[f"metadata[{key}]"] = str(value)
        
        logger.info("Creating payment intent", extra={
            "amount_cents": amount_cents,
            "currency": currency,
            "idempotency_key": idempotency_key
        })
        
        return await self._request(
            "POST",
            "/payment_intents",
            idempotency_key=idempotency_key,
            data=data
        )
    
    async def get_payment_intent(self, intent_id: str) -> dict:
        """Retrieve a PaymentIntent"""
        return await self._request("GET", f"/payment_intents/{intent_id}")
    
    async def cancel_payment_intent(self, intent_id: str) -> dict:
        """Cancel a PaymentIntent"""
        return await self._request("POST", f"/payment_intents/{intent_id}/cancel")
```

---

## Service Layer

```python
# services/payment_service.py
from decimal import Decimal
from datetime import datetime
from typing import Optional
from repositories.payment_repository import PaymentRepository
from clients.stripe_client import StripeClient
from models.payment import Payment, PaymentStatus
from schemas.payment import PaymentCreate, PaymentResponse
from core.exceptions import NotFoundError, ConflictError, ValidationError
import logging

logger = logging.getLogger(__name__)

class PaymentService:
    # Map Stripe status to our status
    STRIPE_STATUS_MAP = {
        "requires_payment_method": PaymentStatus.PENDING,
        "requires_confirmation": PaymentStatus.PENDING,
        "requires_action": PaymentStatus.PROCESSING,
        "processing": PaymentStatus.PROCESSING,
        "succeeded": PaymentStatus.SUCCEEDED,
        "canceled": PaymentStatus.CANCELED,
    }
    
    def __init__(
        self,
        payment_repo: PaymentRepository,
        stripe_client: StripeClient,
        user_service: UserService
    ):
        self.payment_repo = payment_repo
        self.stripe_client = stripe_client
        self.user_service = user_service
    
    async def create_payment(
        self,
        user_id: int,
        data: PaymentCreate
    ) -> Payment:
        """
        Create a payment intent.
        
        Uses idempotency key to prevent duplicate payments.
        """
        # Check for existing payment with same idempotency key
        existing = await self.payment_repo.get_by_idempotency_key(data.idempotency_key)
        if existing:
            logger.info("Returning existing payment for idempotency key", extra={
                "idempotency_key": data.idempotency_key,
                "payment_id": existing.id
            })
            return existing
        
        # Get user's Stripe customer ID
        user = await self.user_service.get_user(user_id)
        if not user:
            raise NotFoundError("User not found")
        
        # Validate amount
        if data.amount <= 0:
            raise ValidationError("Amount must be positive")
        
        # Create local payment record (pending)
        payment = await self.payment_repo.create(
            idempotency_key=data.idempotency_key,
            user_id=user_id,
            order_id=data.order_id,
            amount=data.amount,
            currency=data.currency,
            status=PaymentStatus.PENDING,
            stripe_customer_id=user.stripe_customer_id,
            metadata_=data.metadata
        )
        
        logger.info("Created payment record", extra={
            "payment_id": payment.id,
            "amount": str(data.amount)
        })
        
        try:
            # Create Stripe PaymentIntent
            amount_cents = int(data.amount * 100)
            intent = await self.stripe_client.create_payment_intent(
                amount_cents=amount_cents,
                currency=data.currency,
                customer_id=user.stripe_customer_id,
                idempotency_key=data.idempotency_key,
                metadata={"payment_id": str(payment.id), "order_id": str(data.order_id)}
            )
            
            # Update local record with Stripe ID
            await self.payment_repo.update_status(
                payment,
                status=self._map_stripe_status(intent["status"]),
                stripe_payment_intent_id=intent["id"],
                last_synced_at=datetime.utcnow()
            )
            
            logger.info("Created Stripe payment intent", extra={
                "payment_id": payment.id,
                "stripe_intent_id": intent["id"],
                "stripe_status": intent["status"]
            })
            
        except Exception as e:
            # Record the error but don't fail completely
            # Payment can be retried or synced later
            logger.error("Failed to create Stripe payment intent", extra={
                "payment_id": payment.id,
                "error": str(e)
            })
            
            await self.payment_repo.update_status(
                payment,
                status=PaymentStatus.PENDING,
                error_message=f"Stripe creation failed: {str(e)}"
            )
        
        return payment
    
    async def get_payment(self, payment_id: int) -> Payment:
        """Get payment by ID"""
        payment = await self.payment_repo.get_by_id(payment_id)
        if not payment:
            raise NotFoundError(f"Payment {payment_id} not found")
        return payment
    
    async def get_payment_status(self, payment_id: int) -> dict:
        """Get payment status, optionally syncing with Stripe"""
        payment = await self.get_payment(payment_id)
        
        is_terminal = payment.status in [
            PaymentStatus.SUCCEEDED,
            PaymentStatus.FAILED,
            PaymentStatus.CANCELED,
            PaymentStatus.REFUNDED
        ]
        
        return {
            "payment_id": payment.id,
            "status": payment.status.value,
            "is_terminal": is_terminal,
            "error_message": payment.error_message,
            "last_synced_at": payment.last_synced_at
        }
    
    async def sync_payment(self, payment: Payment) -> Payment:
        """Sync payment status with Stripe"""
        if not payment.stripe_payment_intent_id:
            logger.warning("Cannot sync payment without Stripe ID", extra={
                "payment_id": payment.id
            })
            return payment
        
        try:
            intent = await self.stripe_client.get_payment_intent(
                payment.stripe_payment_intent_id
            )
            
            new_status = self._map_stripe_status(intent["status"])
            
            update_kwargs = {"last_synced_at": datetime.utcnow()}
            
            if intent["status"] == "succeeded":
                update_kwargs["processed_at"] = datetime.utcnow()
            
            if intent.get("last_payment_error"):
                update_kwargs["error_code"] = intent["last_payment_error"].get("code")
                update_kwargs["error_message"] = intent["last_payment_error"].get("message")
            
            payment = await self.payment_repo.update_status(
                payment,
                status=new_status,
                **update_kwargs
            )
            
            logger.info("Synced payment with Stripe", extra={
                "payment_id": payment.id,
                "status": new_status.value
            })
            
        except Exception as e:
            logger.error("Failed to sync payment", extra={
                "payment_id": payment.id,
                "error": str(e)
            })
        
        return payment
    
    async def handle_webhook_event(self, event_type: str, data: dict) -> None:
        """Handle Stripe webhook events"""
        payment_intent_id = data.get("id")
        
        if not payment_intent_id:
            logger.warning("Webhook event missing payment intent ID")
            return
        
        payment = await self.payment_repo.get_by_stripe_intent_id(payment_intent_id)
        
        if not payment:
            logger.warning("Payment not found for webhook", extra={
                "stripe_intent_id": payment_intent_id
            })
            return
        
        logger.info("Processing webhook event", extra={
            "event_type": event_type,
            "payment_id": payment.id
        })
        
        if event_type == "payment_intent.succeeded":
            await self.payment_repo.update_status(
                payment,
                status=PaymentStatus.SUCCEEDED,
                processed_at=datetime.utcnow(),
                last_synced_at=datetime.utcnow()
            )
        
        elif event_type == "payment_intent.payment_failed":
            error = data.get("last_payment_error", {})
            await self.payment_repo.update_status(
                payment,
                status=PaymentStatus.FAILED,
                error_code=error.get("code"),
                error_message=error.get("message"),
                last_synced_at=datetime.utcnow()
            )
        
        elif event_type == "payment_intent.canceled":
            await self.payment_repo.update_status(
                payment,
                status=PaymentStatus.CANCELED,
                last_synced_at=datetime.utcnow()
            )
    
    def _map_stripe_status(self, stripe_status: str) -> PaymentStatus:
        return self.STRIPE_STATUS_MAP.get(stripe_status, PaymentStatus.PENDING)
```

---

## API Routes

```python
# routes/payments.py
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from services.payment_service import PaymentService
from schemas.payment import PaymentCreate, PaymentResponse, PaymentStatusResponse
from dependencies import get_payment_service, get_current_user, get_db
from models.user import User
import stripe
import logging

router = APIRouter(prefix="/payments", tags=["payments"])
logger = logging.getLogger(__name__)

@router.post("", response_model=PaymentResponse, status_code=201)
async def create_payment(
    data: PaymentCreate,
    current_user: User = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """
    Create a new payment.
    
    The idempotency_key ensures that retrying this request won't create
    duplicate payments.
    """
    payment = await payment_service.create_payment(
        user_id=current_user.id,
        data=data
    )
    return payment

@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """Get payment details"""
    payment = await payment_service.get_payment(payment_id)
    
    # Authorization: User can only see their own payments
    if payment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(403, "Access denied")
    
    return payment

@router.get("/{payment_id}/status", response_model=PaymentStatusResponse)
async def get_payment_status(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """
    Get payment status.
    
    For pending payments, this may trigger a sync with Stripe.
    """
    payment = await payment_service.get_payment(payment_id)
    
    if payment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(403, "Access denied")
    
    # Sync if pending and not recently synced
    if payment.status == PaymentStatus.PENDING:
        if not payment.last_synced_at or \
           (datetime.utcnow() - payment.last_synced_at).seconds > 30:
            payment = await payment_service.sync_payment(payment)
    
    return await payment_service.get_payment_status(payment_id)

# Webhook endpoint
@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="Stripe-Signature"),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """Handle Stripe webhook events"""
    payload = await request.body()
    
    try:
        event = stripe.Webhook.construct_event(
            payload,
            stripe_signature,
            settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("Invalid Stripe webhook signature")
        raise HTTPException(400, "Invalid signature")
    
    logger.info("Received Stripe webhook", extra={
        "event_type": event["type"],
        "event_id": event["id"]
    })
    
    # Handle relevant events
    if event["type"] in [
        "payment_intent.succeeded",
        "payment_intent.payment_failed",
        "payment_intent.canceled"
    ]:
        await payment_service.handle_webhook_event(
            event["type"],
            event["data"]["object"]
        )
    
    return {"received": True}
```

---

## Background Sync Job

```python
# tasks/payment_sync.py
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)

async def sync_pending_payments():
    """
    Background job to sync pending payments with Stripe.
    
    Runs as backup to webhooks - catches any missed events.
    """
    logger.info("Starting payment sync job")
    
    async with get_db_session() as session:
        payment_repo = PaymentRepository(session)
        stripe_client = get_stripe_client()
        payment_service = PaymentService(payment_repo, stripe_client, ...)
        
        pending = await payment_repo.get_pending_payments(
            older_than_minutes=5,
            limit=100
        )
        
        logger.info(f"Found {len(pending)} pending payments to sync")
        
        for payment in pending:
            try:
                await payment_service.sync_payment(payment)
                await asyncio.sleep(0.1)  # Rate limiting
            except Exception as e:
                logger.error("Failed to sync payment", extra={
                    "payment_id": payment.id,
                    "error": str(e)
                })
        
        await session.commit()
    
    logger.info("Payment sync job completed")

# Schedule to run every 5 minutes
async def payment_sync_scheduler():
    while True:
        try:
            await sync_pending_payments()
        except Exception as e:
            logger.error(f"Payment sync scheduler error: {e}")
        
        await asyncio.sleep(300)  # 5 minutes
```

---

## Design Decision Explanations

### Why Idempotency Keys?

"In a real payment system, network failures happen. If a client sends a payment request and the response is lost, they'll retry. Without idempotency, we'd charge them twice. The idempotency key ensures that even with retries, we only process each unique payment once."

### Why Local Database Before Stripe?

"We create the local record first for two reasons: (1) We have a record even if Stripe fails, allowing retry. (2) We can track the payment throughout its lifecycle. Stripe is the source of truth for payment status, but our database tracks the business context."

### Why Webhooks AND Polling?

"Webhooks are faster but can be missed (network issues, our service down). Polling is reliable but slower. Using both gives us the best of both worlds - instant updates via webhooks, with polling as a safety net."

### Why Map Stripe Statuses to Our Own?

"Stripe has many detailed statuses that might change. By mapping to our own enum, we decouple our business logic from Stripe's API. If Stripe adds new statuses, we handle them in one place."

---

## Testing the Payment System

```python
# tests/integration/test_payments.py
import pytest
from unittest.mock import AsyncMock
from decimal import Decimal

@pytest.fixture
def mock_stripe_client():
    client = AsyncMock()
    client.create_payment_intent.return_value = {
        "id": "pi_test123",
        "status": "requires_payment_method"
    }
    return client

@pytest.mark.asyncio
async def test_create_payment_success(client, mock_stripe_client, test_user):
    # Override Stripe dependency
    app.dependency_overrides[get_stripe_client] = lambda: mock_stripe_client
    
    response = await client.post(
        "/payments",
        json={
            "order_id": 1,
            "amount": "99.99",
            "idempotency_key": "test-key-123456789"
        },
        headers={"Authorization": f"Bearer {create_token(test_user.id)}"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert data["stripe_payment_intent_id"] == "pi_test123"
    
    mock_stripe_client.create_payment_intent.assert_called_once()

@pytest.mark.asyncio
async def test_create_payment_idempotency(client, mock_stripe_client, test_user):
    idempotency_key = "test-idempotent-key-12345"
    
    # First request
    response1 = await client.post(
        "/payments",
        json={"order_id": 1, "amount": "50.00", "idempotency_key": idempotency_key},
        headers={"Authorization": f"Bearer {create_token(test_user.id)}"}
    )
    
    # Second request with same key
    response2 = await client.post(
        "/payments",
        json={"order_id": 1, "amount": "50.00", "idempotency_key": idempotency_key},
        headers={"Authorization": f"Bearer {create_token(test_user.id)}"}
    )
    
    assert response1.json()["id"] == response2.json()["id"]
    # Stripe should only be called once
    assert mock_stripe_client.create_payment_intent.call_count == 1

@pytest.mark.asyncio
async def test_webhook_updates_payment(client, db_session, test_user):
    # Create a payment first
    payment = Payment(
        idempotency_key="webhook-test-key",
        user_id=test_user.id,
        order_id=1,
        amount=Decimal("100.00"),
        status=PaymentStatus.PENDING,
        stripe_payment_intent_id="pi_webhook_test"
    )
    db_session.add(payment)
    await db_session.commit()
    
    # Simulate webhook
    webhook_payload = {
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_webhook_test"}}
    }
    
    response = await client.post(
        "/payments/webhooks/stripe",
        json=webhook_payload,
        headers={"Stripe-Signature": create_test_signature(webhook_payload)}
    )
    
    assert response.status_code == 200
    
    # Verify payment updated
    await db_session.refresh(payment)
    assert payment.status == PaymentStatus.SUCCEEDED
```

---

## Production Considerations

### Monitoring
- Track payment creation rate, success rate, failure reasons
- Alert on elevated failure rates
- Monitor Stripe API latency and errors

### Security
- Validate webhook signatures
- Never log full card details
- Use HTTPS for all communication
- Encrypt sensitive data at rest

### Compliance
- PCI DSS: Card data never touches your servers (use Stripe Elements)
- Keep audit logs of all payment operations
- Support chargebacks and disputes

### Disaster Recovery
- What if Stripe is down? Queue payments for later
- What if our database is down? Return errors, don't lose data
- Reconciliation job to catch discrepancies

---

This capstone project demonstrates how all the patterns we've learned come together in a real production system. The key is understanding not just the code, but the reasoning behind each decision.
