"""
Web hosted-checkout billing (browser client only).

This is ADDITIVE and completely separate from the Apple-native iOS billing
path in api/payments.py. Every endpoint here is gated behind
`settings.stripe_web_billing_enabled` AND a configured Stripe secret key, so
with the default config it is inert (503) even if deployed. It never touches
`STRIPE_BILLING_RETIRED` or any Apple code path, and it refuses to act on
Apple-billed users. Fulfillment reuses the existing, already-deployed Stripe
webhook (`checkout.session.completed` → `_activate_user`).
"""

import logging
from urllib.parse import urljoin

import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from middleware import get_current_user
from services.stripe_service import stripe_service
from config import settings
from api.payments import _ensure_stripe_customer, _is_apple_billed_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments/web", tags=["Payments (web)"])


def _web_billing_ready() -> bool:
    """Web checkout is usable only when explicitly enabled AND keyed."""
    return bool(settings.stripe_web_billing_enabled and settings.stripe_secret_key)


def _require_web_billing() -> None:
    if not _web_billing_ready():
        # 503: the feature exists but is turned off / not configured. The web
        # client treats 503 and 404 identically as "coming soon".
        raise HTTPException(status_code=503, detail="web_billing_disabled")


def _safe_redirect_url(path: str) -> str:
    """Join a client-supplied RELATIVE path onto web_app_url. Rejects absolute
    or protocol-relative URLs so a caller can't turn this into an open redirect."""
    base = (settings.web_app_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="web_app_url_not_configured")
    p = path or "/"
    if not p.startswith("/") or p.startswith("//") or "://" in p:
        p = "/"
    return urljoin(base + "/", p.lstrip("/"))


class CheckoutRequest(BaseModel):
    tier: str = "premium"
    success_path: str = "/subscribe/success"
    cancel_path: str = "/subscribe"


@router.get("/config")
async def web_billing_config(current_user: dict = Depends(get_current_user)):
    """Lets the web client render the real checkout vs a 'coming soon' state
    without probing the checkout endpoint."""
    return {"enabled": _web_billing_ready()}


@router.post("/checkout")
async def create_web_checkout(
    body: CheckoutRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a hosted Stripe Checkout Session for a web subscription.

    Fulfillment is handled by the EXISTING deployed webhook, which reads
    `metadata.user_id` off `checkout.session.completed` and calls
    `_activate_user`. This endpoint only mints the session.
    """
    _require_web_billing()

    # Never let a web card sub collide with an active Apple subscription.
    if _is_apple_billed_user(current_user):
        raise HTTPException(status_code=409, detail="apple_billing")
    if current_user.get("is_paid"):
        raise HTTPException(status_code=409, detail="already_subscribed")

    tier = body.tier if body.tier in ("basic", "premium") else "premium"
    try:
        price_id = stripe_service.resolve_price_id(tier)
    except ValueError:
        # Price IDs not configured → treat as not-yet-available, not a 500.
        raise HTTPException(status_code=503, detail="web_billing_disabled")

    customer_id = await _ensure_stripe_customer(current_user, db)
    success_url = _safe_redirect_url(body.success_path)
    cancel_url = _safe_redirect_url(body.cancel_path)

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": str(current_user["id"]), "tier": tier},
            subscription_data={"metadata": {"user_id": str(current_user["id"]), "tier": tier}},
            allow_promotion_codes=True,
        )
    except Exception:
        logger.exception("web checkout session create failed")
        raise HTTPException(status_code=502, detail="checkout_unavailable")

    return {"checkout_url": session.url}


@router.post("/cancel")
async def cancel_web_subscription(
    current_user: dict = Depends(get_current_user),
):
    """Cancel a web (Stripe) subscription at period end. Apple-billed users are
    refused — they manage through the App Store."""
    _require_web_billing()
    if (current_user.get("billing_provider") or "").lower() != "stripe":
        raise HTTPException(status_code=409, detail="not_stripe_billed")
    sub_id = current_user.get("subscription_id")
    if not sub_id:
        raise HTTPException(status_code=409, detail="no_subscription")
    ok = await stripe_service.cancel_subscription(sub_id, at_period_end=True)
    return {"canceled": bool(ok), "at_period_end": True}


@router.post("/resume")
async def resume_web_subscription(
    current_user: dict = Depends(get_current_user),
):
    """Undo a pending cancellation on a web (Stripe) subscription."""
    _require_web_billing()
    if (current_user.get("billing_provider") or "").lower() != "stripe":
        raise HTTPException(status_code=409, detail="not_stripe_billed")
    sub_id = current_user.get("subscription_id")
    if not sub_id:
        raise HTTPException(status_code=409, detail="no_subscription")
    ok = await stripe_service.resume_subscription(sub_id)
    return {"resumed": bool(ok)}
