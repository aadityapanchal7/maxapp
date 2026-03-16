"""
Payments API - Stripe subscriptions
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db
from middleware import get_current_user
from services.stripe_service import stripe_service
from models.payment import PaymentCreate, CheckoutSessionResponse
from models.sqlalchemy_models import User, Scan

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/create-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    data: PaymentCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create Stripe checkout session for subscription"""
    user_id = current_user["id"]
    
    # Get or create Stripe customer
    customer_id = current_user.get("stripe_customer_id")
    if not customer_id:
        customer_id = await stripe_service.create_customer(current_user["email"], user_id)
        user = await db.get(User, UUID(user_id))
        if user:
            user.stripe_customer_id = customer_id
            await db.commit()
    
    session_id, checkout_url = await stripe_service.create_checkout_session(
        customer_id, data.success_url, data.cancel_url, user_id
    )
    
    return CheckoutSessionResponse(session_id=session_id, checkout_url=checkout_url)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Stripe webhooks"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe_service.construct_webhook_event(payload, sig_header)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {e}")
    
    result = await stripe_service.handle_webhook_event(event)
    
    if result.get("action") == "activate" and result.get("user_id"):
        try:
            user_uuid = UUID(result["user_id"])
        except ValueError:
            return {"status": "ok"}

        user = await db.get(User, user_uuid)
        if user:
            user.is_paid = True
            user.subscription_id = result.get("subscription_id")
            user.subscription_status = "active"
            await db.commit()

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
    db: AsyncSession = Depends(get_db),
):
    """
    DEV ONLY: Manually activate subscription for testing.
    This bypasses Stripe webhooks which don't work on localhost.
    """
    from config import settings
    env = (settings.app_env or "").lower()
    if env not in ("development", "dev") and not getattr(settings, "debug", False):
        raise HTTPException(status_code=403, detail="Only available in development mode")
    
    user_id = current_user["id"]
    
    try:
        user = await db.get(User, UUID(user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_paid = True
        user.subscription_status = "active"
        await db.commit()

        scans_result = await db.execute(select(Scan).where(Scan.user_id == UUID(user_id)))
        for scan in scans_result.scalars().all():
            scan.is_unlocked = True
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        print(f"[ERROR] test-activate failed: {e}")
        raise HTTPException(status_code=500, detail=f"Activation failed: {e}")
    
    return {"status": "activated", "message": "Subscription activated for testing"}
