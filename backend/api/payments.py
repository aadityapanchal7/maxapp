"""
Payments API — Stripe SetupIntent + Subscription flow
"""

import logging
from fastapi import APIRouter, HTTPException, Request, Depends
from uuid import UUID
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db
from middleware import get_current_user
from services.stripe_service import stripe_service
from models.payment import (
    PaymentCreate,
    CheckoutSessionResponse,
    BillingPreviewRequest,
    BillingPreviewResponse,
    SubscribeRequest,
    SubscribeResponse,
    CancelRequest,
    CancelResponse,
)
from models.sqlalchemy_models import User, Scan
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _ensure_stripe_customer(
    current_user: dict, db: AsyncSession
) -> str:
    """Return existing Stripe customer_id or create one and persist it."""
    customer_id = current_user.get("stripe_customer_id")
    if customer_id:
        return customer_id
    customer_id = await stripe_service.create_customer(
        current_user["email"], current_user["id"]
    )
    user = await db.get(User, UUID(current_user["id"]))
    if user:
        user.stripe_customer_id = customer_id
        await db.commit()
    return customer_id


async def _activate_user(user_id: str, subscription_id: str | None, db: AsyncSession):
    """Shared activation logic for webhook + test-activate."""
    user_uuid = UUID(user_id)
    user = await db.get(User, user_uuid)
    if not user:
        return
    user.is_paid = True
    if subscription_id:
        user.subscription_id = subscription_id
    user.subscription_status = "active"
    ob = dict(user.onboarding or {})
    ob["post_subscription_onboarding"] = True
    ob["sendblue_connect_completed"] = False
    user.onboarding = ob
    await db.commit()

    scans_result = await db.execute(
        select(Scan).where(Scan.user_id == user_uuid)
    )
    for scan in scans_result.scalars().all():
        scan.is_unlocked = True
    await db.commit()


async def _deactivate_user(user_id: str, db: AsyncSession):
    user = await db.get(User, UUID(user_id))
    if not user:
        return
    user.is_paid = False
    user.subscription_status = "canceled"
    await db.commit()


# ------------------------------------------------------------------
# Native flow: billing-preview → Payment Sheet
# ------------------------------------------------------------------

@router.post("/billing-preview", response_model=BillingPreviewResponse)
async def billing_preview(
    body: BillingPreviewRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the three secrets that Payment Sheet needs:
    customerId, ephemeralKeySecret, setupIntentClientSecret.
    """
    customer_id = await _ensure_stripe_customer(current_user, db)
    ephemeral_secret = await stripe_service.create_ephemeral_key(customer_id)
    si_id, si_secret = await stripe_service.create_setup_intent(
        customer_id, current_user["id"]
    )
    return BillingPreviewResponse(
        customer_id=customer_id,
        ephemeral_key_secret=ephemeral_secret,
        setup_intent_client_secret=si_secret,
        setup_intent_id=si_id,
        publishable_key=settings.stripe_publishable_key,
    )


# ------------------------------------------------------------------
# Native flow: subscribe (after Payment Sheet succeeds)
# ------------------------------------------------------------------

@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    body: SubscribeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    After the client confirms a SetupIntent, call this to create the
    weekly Subscription on the saved payment method.
    """
    user_id = current_user["id"]

    if current_user.get("is_paid"):
        raise HTTPException(status_code=409, detail="Already subscribed")

    si = await stripe_service.get_setup_intent(body.setup_intent_id)

    if si.status != "succeeded":
        raise HTTPException(status_code=400, detail="SetupIntent has not succeeded yet")

    customer_id = current_user.get("stripe_customer_id")
    if not customer_id or si.customer != customer_id:
        raise HTTPException(status_code=403, detail="SetupIntent does not belong to this user")

    price_id = stripe_service.resolve_price_id(body.tier)
    pm_id = si.payment_method

    sub = await stripe_service.create_subscription(
        customer_id=customer_id,
        price_id=price_id,
        payment_method_id=pm_id,
        user_id=user_id,
    )

    if sub.status == "active":
        await _activate_user(user_id, sub.id, db)

    return SubscribeResponse(subscription_id=sub.id, status=sub.status)


# ------------------------------------------------------------------
# Cancel
# ------------------------------------------------------------------

@router.post("/cancel", response_model=CancelResponse)
async def cancel_subscription(
    body: CancelRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub_id = current_user.get("subscription_id")
    if not sub_id:
        raise HTTPException(status_code=404, detail="No active subscription")

    ok = await stripe_service.cancel_subscription(sub_id, at_period_end=not body.immediate)

    if not ok:
        raise HTTPException(status_code=500, detail="Could not cancel subscription")

    if body.immediate:
        await _deactivate_user(current_user["id"], db)

    return CancelResponse(canceled=True)


# ------------------------------------------------------------------
# Webhook
# ------------------------------------------------------------------

@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe_service.construct_webhook_event(payload, sig_header)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {e}")

    result = await stripe_service.handle_webhook_event(event)
    action = result.get("action")
    uid = result.get("user_id")
    sub_id = result.get("subscription_id")

    if action == "activate" and uid:
        await _activate_user(uid, sub_id, db)

    elif action == "cancel" and uid:
        await _deactivate_user(uid, db)

    elif action == "payment_failed" and uid:
        user = await db.get(User, UUID(uid))
        if user:
            user.subscription_status = result.get("status") or "past_due"
            await db.commit()

    return {"status": "ok"}


# ------------------------------------------------------------------
# Status (existing)
# ------------------------------------------------------------------

@router.get("/status")
async def get_subscription_status(current_user: dict = Depends(get_current_user)):
    sub_id = current_user.get("subscription_id")
    if not sub_id:
        return {"is_active": False}

    sub = await stripe_service.get_subscription(sub_id)
    return {
        "is_active": sub.get("status") == "active" if sub else False,
        "subscription": sub,
    }


# ------------------------------------------------------------------
# Legacy: embedded Checkout session
# ------------------------------------------------------------------

@router.post("/create-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    data: PaymentCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"]
    customer_id = await _ensure_stripe_customer(current_user, db)

    session_id, client_secret = await stripe_service.create_checkout_session(
        customer_id, data.success_url, user_id
    )
    return CheckoutSessionResponse(session_id=session_id, checkout_url=client_secret)


# ------------------------------------------------------------------
# DEV ONLY: test-activate (bypass Stripe)
# ------------------------------------------------------------------

class TestActivateBody(BaseModel):
    tier: str = "premium"


@router.post("/test-activate")
async def test_activate_subscription(
    body: TestActivateBody = TestActivateBody(),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from config import settings as _s
    env = (_s.app_env or "").lower()
    if env not in ("development", "dev") and not getattr(_s, "debug", False):
        raise HTTPException(status_code=403, detail="Only available in development mode")

    try:
        await _activate_user(current_user["id"], None, db)
    except Exception as e:
        await db.rollback()
        logger.error(f"test-activate failed: {e}")
        raise HTTPException(status_code=500, detail=f"Activation failed: {e}")

    return {"status": "activated", "tier": body.tier, "message": f"Subscription activated as {body.tier} for testing"}
