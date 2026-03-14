"""
Payments API - Stripe subscriptions
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from db import get_db
from middleware.auth_middleware import get_current_user
from services.stripe_service import stripe_service
from models.sqlalchemy_models import User, Payment, Scan

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/create-session")
async def create_checkout_session(
    data: dict = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create Stripe checkout session for subscription"""
    if data is None:
        data = {}

    user_id = current_user["id"]
    user_uuid = UUID(user_id)

    # Get or create Stripe customer
    customer_id = current_user.get("stripe_customer_id")
    if not customer_id:
        customer_id = await stripe_service.create_customer(current_user["email"], user_id)
        user = await db.get(User, user_uuid)
        if user:
            user.stripe_customer_id = customer_id
            await db.commit()

    session_id, checkout_url = await stripe_service.create_checkout_session(
        customer_id, data.get("success_url"), data.get("cancel_url"), user_id
    )

    return {"session_id": session_id, "checkout_url": checkout_url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle Stripe webhooks"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe_service.construct_webhook_event(payload, sig_header)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {e}")

    result = await stripe_service.handle_webhook_event(event)

    if result.get("action") == "activate" and result.get("user_id"):
        user_id = result["user_id"]
        user_uuid = UUID(user_id)

        user = await db.get(User, user_uuid)
        if user:
            user.is_paid = True
            user.subscription_id = result.get("subscription_id")
            user.subscription_status = "active"
            await db.commit()

            # Unlock all scans for user
            scans_result = await db.execute(
                select(Scan).where(Scan.user_id == user_uuid)
            )
            for scan in scans_result.scalars().all():
                scan.is_unlocked = True
            await db.commit()

    return {"status": "ok"}


@router.get("/status")
async def get_subscription_status(current_user: dict = Depends(get_current_user)):
    """Get subscription status"""
    sub_id = current_user.get("subscription_id")
    if not sub_id:
        return {"is_active": False}

    sub = await stripe_service.get_subscription(sub_id)
    return {"is_active": sub.get("status") == "active" if sub else False, "subscription": sub}


@router.post("/test-activate")
async def test_activate_subscription(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    DEV ONLY: Manually activate subscription for testing.
    This bypasses Stripe webhooks which don't work on localhost.
    """
    from config import settings
    if settings.app_env != "development":
        raise HTTPException(status_code=403, detail="Only available in development mode")

    user_id = current_user["id"]
    user_uuid = UUID(user_id)

    # Activate user
    user = await db.get(User, user_uuid)
    if user:
        user.is_paid = True
        user.subscription_status = "active"
        await db.commit()

        # Unlock all scans
        scans_result = await db.execute(
            select(Scan).where(Scan.user_id == user_uuid)
        )
        for scan in scans_result.scalars().all():
            scan.is_unlocked = True
        await db.commit()

    return {"status": "activated", "message": "Subscription activated for testing"}
