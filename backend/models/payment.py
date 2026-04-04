"""
Payment Models — Stripe SetupIntent + Subscription flow
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    PAST_DUE = "past_due"
    PAUSED = "paused"
    TRIALING = "trialing"
    UNPAID = "unpaid"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


# --------------- Legacy (embedded checkout) ---------------

class PaymentCreate(BaseModel):
    success_url: str = Field(description="URL to redirect after successful payment")
    cancel_url: str = Field(description="URL to redirect if payment is canceled")


class CheckoutSessionResponse(BaseModel):
    session_id: str
    checkout_url: str


# --------------- Native flow: billing-preview ---------------

class BillingPreviewRequest(BaseModel):
    tier: Literal["basic", "premium"] = Field(description="Subscription tier")


class BillingPreviewResponse(BaseModel):
    customer_id: str
    ephemeral_key_secret: str
    setup_intent_client_secret: str
    setup_intent_id: str
    publishable_key: str


# --------------- Native flow: subscribe ---------------

class SubscribeRequest(BaseModel):
    tier: Literal["basic", "premium"]
    setup_intent_id: str = Field(description="SetupIntent confirmed on the client")


class SubscribeResponse(BaseModel):
    subscription_id: str
    status: str


# --------------- Native flow: cancel ---------------

class CancelRequest(BaseModel):
    immediate: bool = Field(default=False, description="Cancel now vs at period end")


class CancelResponse(BaseModel):
    canceled: bool


# --------------- Change tier / resume ---------------

class ChangeTierRequest(BaseModel):
    tier: Literal["basic", "premium"]


class ChangeTierResponse(BaseModel):
    status: str
    subscription_tier: str


class ResumeSubscriptionResponse(BaseModel):
    resumed: bool


# --------------- Shared / status ---------------

class SubscriptionResponse(BaseModel):
    is_active: bool
    status: Optional[SubscriptionStatus] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False


class PaymentResponse(BaseModel):
    id: str
    user_id: str
    stripe_subscription_id: Optional[str] = None
    amount: float
    currency: str
    status: PaymentStatus
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentInDB(BaseModel):
    user_id: str
    stripe_customer_id: Optional[str] = None
    stripe_session_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_payment_intent: Optional[str] = None
    amount: float
    currency: str = "usd"
    status: PaymentStatus = PaymentStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    subscription_status: Optional[SubscriptionStatus] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None


class WebhookEvent(BaseModel):
    event_type: str
    event_id: str
    data: dict
