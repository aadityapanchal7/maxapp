"""
Payments API — Stripe SetupIntent + Subscription flow
"""

import logging
import stripe
from fastapi import APIRouter, HTTPException, Request, Depends
from uuid import UUID
from pydantic import BaseModel
from typing import Optional
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
    ChangeTierRequest,
    ChangeTierResponse,
    ResumeSubscriptionResponse,
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


async def _activate_user(
    user_id: str,
    subscription_id: str | None,
    db: AsyncSession,
    subscription_tier: Optional[str] = None,
):
    """Shared activation logic for webhook + test-activate.

    Idempotent: Stripe can redeliver the same event, and this function is
    also reachable via multiple webhook handlers. We only touch the
    onboarding flags the *first* time a user activates — otherwise a
    duplicate delivery would silently flip `sendblue_connect_completed`
    back to False and bounce the user back through the SMS-connect step.
    """
    user_uuid = UUID(user_id)
    user = await db.get(User, user_uuid)
    if not user:
        return
    was_already_paid = bool(user.is_paid)
    user.is_paid = True
    if subscription_id:
        user.subscription_id = subscription_id
    user.subscription_status = "active"
    if subscription_tier in ("basic", "premium"):
        user.subscription_tier = subscription_tier
    if not was_already_paid:
        ob = dict(user.onboarding or {})
        ob["post_subscription_onboarding"] = True
        # Only initialize the flag if it has never been set. If the user has
        # already finished the Sendblue step (True) or explicitly skipped it,
        # don't clobber their progress on a webhook replay.
        # Use explicit None check instead of setdefault because OnboardingData
        # serializes the field as None by default — setdefault treats that as
        # "already set" and leaves it as None, causing the mobile client to
        # skip the SendblueConnect screen (null !== false).
        if ob.get("sendblue_connect_completed") is None:
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
    user.subscription_id = None
    user.subscription_tier = None
    await db.commit()


async def _sync_subscription_tier_from_stripe(user_id: str, subscription_id: str, db: AsyncSession) -> None:
    try:
        sub = stripe_service.retrieve_subscription_object(subscription_id)
        tier = stripe_service.tier_from_subscription(sub)
        if not tier:
            return
        user = await db.get(User, UUID(user_id))
        if user:
            user.subscription_tier = tier
            await db.commit()
    except Exception as e:
        logger.warning("Could not sync subscription tier from Stripe: %s", e)


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
        subscription_tier=body.tier,
    )

    if sub.status in ("active", "trialing"):
        await _activate_user(user_id, sub.id, db, subscription_tier=body.tier)

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
    event_type = result.get("event_type")

    if action == "activate" and uid:
        await _activate_user(uid, sub_id, db)
        if sub_id:
            await _sync_subscription_tier_from_stripe(uid, sub_id, db)

    elif action == "cancel" and uid:
        await _deactivate_user(uid, db)

    elif action == "payment_failed" and uid:
        user = await db.get(User, UUID(uid))
        if user:
            user.subscription_status = result.get("status") or "past_due"
            await db.commit()

    if (
        uid
        and sub_id
        and event_type == "customer.subscription.updated"
        and action == "update"
    ):
        await _sync_subscription_tier_from_stripe(uid, sub_id, db)

    return {"status": "ok"}


# ------------------------------------------------------------------
# Status (existing)
# ------------------------------------------------------------------

def _dt_iso(v) -> str | None:
    if v is not None and hasattr(v, "isoformat"):
        return v.isoformat()
    return None


@router.get("/status")
async def get_subscription_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Billing metadata for the manage-subscription UI. JSON-safe; never raises for Stripe quirks.
    """
    user_row = await db.get(User, UUID(current_user["id"]))
    tier = (
        (user_row.subscription_tier if user_row else None)
        or current_user.get("subscription_tier")
    )
    sub_id = (user_row.subscription_id if user_row else None) or current_user.get(
        "subscription_id"
    )
    paid = bool(user_row.is_paid) if user_row else bool(current_user.get("is_paid"))

    if not sub_id:
        end_iso = _dt_iso(user_row.subscription_end_date) if user_row else None
        return {
            "is_active": paid,
            "subscription_tier": tier,
            "cancel_at_period_end": False,
            "current_period_end_iso": end_iso,
            "current_period_start_iso": None,
            "has_stripe_subscription": False,
            "subscription": None,
            "degraded": False,
        }

    try:
        sub = await stripe_service.get_subscription(sub_id)
    except Exception as e:
        logger.exception("get_subscription_status: Stripe retrieve error: %s", e)
        sub = None

    if not sub:
        end_iso = _dt_iso(user_row.subscription_end_date) if user_row else None
        return {
            "is_active": False,
            "subscription_tier": tier,
            "cancel_at_period_end": False,
            "current_period_end_iso": end_iso,
            "current_period_start_iso": None,
            "has_stripe_subscription": True,
            "subscription": None,
            "degraded": True,
        }

    cancel_at = bool(sub.get("cancel_at_period_end"))
    cps = sub.get("current_period_start")
    cpe = sub.get("current_period_end")
    start_iso = _dt_iso(cps)
    end_iso = _dt_iso(cpe)
    stripe_active = sub.get("status") == "active"

    return {
        "is_active": stripe_active,
        "subscription_tier": tier,
        "cancel_at_period_end": cancel_at,
        "current_period_end_iso": end_iso,
        "current_period_start_iso": start_iso,
        "has_stripe_subscription": True,
        "subscription": {
            "id": sub.get("id"),
            "status": sub.get("status"),
            "cancel_at_period_end": cancel_at,
            "current_period_start": start_iso,
            "current_period_end": end_iso,
        },
        "degraded": False,
    }


# ------------------------------------------------------------------
# Change tier (existing subscribers)
# ------------------------------------------------------------------


@router.post("/change-tier", response_model=ChangeTierResponse)
async def change_subscription_tier(
    body: ChangeTierRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub_id = current_user.get("subscription_id")
    if not sub_id:
        raise HTTPException(status_code=404, detail="No active subscription")

    if body.tier not in ("basic", "premium"):
        raise HTTPException(status_code=400, detail="Invalid tier")

    user = await db.get(User, UUID(current_user["id"]))
    current_tier = (
        (user.subscription_tier if user else None) or "basic"
    ).lower()
    if current_tier == body.tier:
        raise HTTPException(status_code=400, detail="Already on this plan")

    try:
        new_price_id = stripe_service.resolve_price_id(body.tier)
        stripe_service.change_subscription_price(sub_id, new_price_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.StripeError as e:
        logger.exception("Stripe change-tier failed")
        raise HTTPException(
            status_code=502,
            detail=getattr(e, "user_message", None) or str(e) or "Payment provider error",
        )

    if user:
        user.subscription_tier = body.tier
        try:
            stripe.Subscription.modify(sub_id, metadata={"tier": body.tier})
        except stripe.error.StripeError:
            pass
        await db.commit()

    return ChangeTierResponse(status="ok", subscription_tier=body.tier)


# ------------------------------------------------------------------
# Resume (undo cancel at period end)
# ------------------------------------------------------------------


@router.post("/resume", response_model=ResumeSubscriptionResponse)
async def resume_subscription(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub_id = current_user.get("subscription_id")
    if not sub_id:
        raise HTTPException(status_code=404, detail="No active subscription")

    sub = await stripe_service.get_subscription(sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if not sub.get("cancel_at_period_end"):
        raise HTTPException(status_code=400, detail="Subscription is not scheduled to cancel")

    ok = await stripe_service.resume_subscription(sub_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Could not resume subscription")

    user = await db.get(User, UUID(current_user["id"]))
    if user:
        user.subscription_status = "active"
        await db.commit()

    return ResumeSubscriptionResponse(resumed=True)


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
        tier = body.tier if body.tier in ("basic", "premium") else "premium"
        await _activate_user(current_user["id"], None, db, subscription_tier=tier)
    except Exception as e:
        await db.rollback()
        logger.error(f"test-activate failed: {e}")
        raise HTTPException(status_code=500, detail=f"Activation failed: {e}")

    return {"status": "activated", "tier": body.tier, "message": f"Subscription activated as {body.tier} for testing"}
