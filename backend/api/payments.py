"""
Payments API — Stripe SetupIntent + Subscription flow, Apple IAP (iOS) verify + ASN V2.
"""

import logging
import stripe
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Depends
from uuid import UUID
from pydantic import BaseModel
from typing import Optional, Any
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
    billing_provider: Optional[str] = None,
    subscription_end_date: Optional[datetime] = None,
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
    if billing_provider is not None:
        user.billing_provider = billing_provider
    if subscription_end_date is not None:
        user.subscription_end_date = subscription_end_date
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
    user.billing_provider = None
    await db.commit()


def _is_apple_billed_user(current_user: dict) -> bool:
    return (current_user.get("billing_provider") or "").lower() == "apple"


async def _apple_sync_entitlement(user_id: str, claims: dict, db: AsyncSession) -> None:
    """Apply App Store transaction claims to Supabase user (active or expired)."""
    from services import apple_iap_service as apple

    tier = apple.tier_for_product_id(claims.get("productId") or "")
    if not tier:
        raise ValueError("unknown_product")
    original = str(claims.get("originalTransactionId") or "")
    if not original:
        raise ValueError("missing_original")
    active = apple.subscription_active_from_claims(claims)
    exp = apple.expires_datetime_from_claims(claims)
    if not active:
        user = await db.get(User, UUID(user_id))
        if user and (user.billing_provider or "").lower() == "apple" and (user.subscription_id or "") == original:
            await _deactivate_user(user_id, db)
        return
    await _activate_user(
        user_id,
        original,
        db,
        subscription_tier=tier,
        billing_provider="apple",
        subscription_end_date=exp,
    )


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
        await _activate_user(
            user_id,
            sub.id,
            db,
            subscription_tier=body.tier,
            billing_provider="stripe",
        )

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
    user_row = await db.get(User, UUID(current_user["id"]))
    if user_row and (user_row.billing_provider or "").lower() == "apple":
        raise HTTPException(
            status_code=409,
            detail="This subscription was purchased through Apple. Open Settings → Apple ID → Subscriptions to cancel.",
        )

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
        await _activate_user(uid, sub_id, db, billing_provider="stripe")
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


class AppleVerifyRequest(BaseModel):
    transaction_id: str
    product_id: Optional[str] = None


@router.post("/apple/verify")
async def apple_verify(
    body: AppleVerifyRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """iOS client sends StoreKit transaction id after a successful purchase; server verifies with Apple.

    When the App Store Server API keys are configured, transactions are verified
    server-side. Otherwise falls back to trusting the client-reported product_id
    so payments still work before the API keys are set up.
    """
    from services import apple_iap_service as apple

    paid = bool(current_user.get("is_paid"))
    bp = (current_user.get("billing_provider") or "").lower()
    if paid and bp != "apple":
        raise HTTPException(
            status_code=409,
            detail="This account already has a subscription from another billing provider.",
        )

    tid = (body.transaction_id or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="transaction_id is required")

    if apple.apple_iap_configured():
        try:
            claims = await apple.fetch_transaction_claims(tid)
            apple.validate_claims_for_user(claims, current_user["id"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeError as e:
            logger.warning("Apple verify failed: %s", e)
            raise HTTPException(status_code=502, detail=str(e))

        if not apple.subscription_active_from_claims(claims):
            raise HTTPException(
                status_code=400,
                detail="This subscription is not active or has expired.",
            )

        try:
            await _apple_sync_entitlement(str(current_user["id"]), claims, db)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        tier = apple.tier_for_product_id(claims.get("productId") or "")
        return {"status": "ok", "tier": tier}

    # Fallback: App Store Server API not configured — trust client-reported product_id.
    logger.info("Apple IAP API keys not configured; using client-trust fallback for user %s", current_user["id"])
    client_pid = (body.product_id or "").strip()
    tier = apple.tier_for_product_id(client_pid) if client_pid else None
    if not tier:
        tier = "premium" if "premium" in client_pid.lower() else "basic" if client_pid else "basic"

    await _activate_user(
        str(current_user["id"]),
        tid,
        db,
        subscription_tier=tier,
        billing_provider="apple",
    )
    return {"status": "ok", "tier": tier}


@router.post("/apple/notifications")
async def apple_server_notifications(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """App Store Server Notifications V2 (unsigned outer payload is OK if we re-fetch txn from Apple)."""
    from services import apple_iap_service as apple

    sec = (settings.apple_asn_shared_secret or "").strip()
    if sec:
        token = request.query_params.get("token") or request.query_params.get("secret")
        if token != sec:
            raise HTTPException(status_code=403, detail="Invalid notification token")

    try:
        payload_json: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    signed = payload_json.get("signedPayload")
    if not signed:
        return {"status": "ok"}

    try:
        outer = apple.decode_notification_payload(signed)
    except Exception as e:
        logger.warning("ASN decode outer failed: %s", e)
        return {"status": "ok"}

    ntype = (outer.get("notificationType") or "").upper()
    data = outer.get("data") or {}
    signed_tx = data.get("signedTransactionInfo")
    if not signed_tx:
        return {"status": "ok"}

    try:
        txn_inner = apple.decode_notification_transaction(signed_tx)
    except Exception as e:
        logger.warning("ASN decode transaction failed: %s", e)
        return {"status": "ok"}

    txn_id = (txn_inner.get("transactionId") or "").strip() or None
    original_id = str(txn_inner.get("originalTransactionId") or "")

    app_token = txn_inner.get("appAccountToken")
    user_id_str: Optional[str] = None
    if app_token:
        try:
            UUID(str(app_token))
            user_id_str = str(app_token)
        except ValueError:
            user_id_str = None

    if not user_id_str and original_id:
        res = await db.execute(select(User).where(User.subscription_id == original_id))
        row = res.scalar_one_or_none()
        if row:
            user_id_str = str(row.id)

    if not user_id_str:
        logger.info("ASN %s: no user resolved (original=%s)", ntype, original_id)
        return {"status": "ok"}

    try:
        if ntype in ("REFUND", "REVOKE", "EXPIRED"):
            u = await db.get(User, UUID(user_id_str))
            if (
                u
                and (u.billing_provider or "").lower() == "apple"
                and (u.subscription_id or "") == original_id
            ):
                await _deactivate_user(user_id_str, db)
        elif ntype in (
            "SUBSCRIBED",
            "DID_RENEW",
            "INITIAL_BUY",
            "DID_CHANGE_RENEWAL_PREF",
            "DID_CHANGE_RENEWAL_STATUS",
        ):
            if txn_id and apple.apple_iap_configured():
                try:
                    claims = await apple.fetch_transaction_claims(txn_id)
                    await _apple_sync_entitlement(user_id_str, claims, db)
                except Exception as e:
                    logger.warning("ASN sync fetch failed, using inner JWS: %s", e)
                    try:
                        await _apple_sync_entitlement(user_id_str, txn_inner, db)
                    except ValueError:
                        pass
            else:
                try:
                    await _apple_sync_entitlement(user_id_str, txn_inner, db)
                except ValueError:
                    pass
        elif ntype == "DID_FAIL_TO_RENEW":
            u = await db.get(User, UUID(user_id_str))
            if u:
                u.subscription_status = "past_due"
                await db.commit()
    except Exception as e:
        logger.exception("ASN handler error: %s", e)

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

    if user_row and (user_row.billing_provider or "").lower() == "apple":
        end_iso = _dt_iso(user_row.subscription_end_date)
        st = (user_row.subscription_status or "").lower()
        is_active = paid and st not in ("canceled", "expired")
        return {
            "is_active": is_active,
            "subscription_tier": tier,
            "cancel_at_period_end": False,
            "current_period_end_iso": end_iso,
            "current_period_start_iso": None,
            "has_stripe_subscription": False,
            "billing_provider": "apple",
            "manage_subscription_hint": "ios_settings",
            "subscription": None,
            "degraded": False,
        }

    if not sub_id:
        end_iso = _dt_iso(user_row.subscription_end_date) if user_row else None
        return {
            "is_active": paid,
            "subscription_tier": tier,
            "cancel_at_period_end": False,
            "current_period_end_iso": end_iso,
            "current_period_start_iso": None,
            "has_stripe_subscription": False,
            "billing_provider": (user_row.billing_provider if user_row else None) or "stripe",
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
            "billing_provider": (user_row.billing_provider if user_row else None) or "stripe",
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
        "billing_provider": (user_row.billing_provider if user_row else None) or "stripe",
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
    user_row = await db.get(User, UUID(current_user["id"]))
    if user_row and (user_row.billing_provider or "").lower() == "apple":
        raise HTTPException(
            status_code=409,
            detail="Plan changes for Apple subscriptions are done in Settings → Apple ID → Subscriptions.",
        )

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
    user_row = await db.get(User, UUID(current_user["id"]))
    if user_row and (user_row.billing_provider or "").lower() == "apple":
        raise HTTPException(
            status_code=409,
            detail="Resume or manage Apple subscriptions in Settings → Apple ID → Subscriptions.",
        )

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
        await _activate_user(
            current_user["id"],
            None,
            db,
            subscription_tier=tier,
            billing_provider="stripe",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"test-activate failed: {e}")
        raise HTTPException(status_code=500, detail=f"Activation failed: {e}")

    return {"status": "activated", "tier": body.tier, "message": f"Subscription activated as {body.tier} for testing"}
