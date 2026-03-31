"""
Stripe Service - Subscription-based payments
"""

import logging
import stripe
from typing import Optional, Tuple
from datetime import datetime
from config import settings

logger = logging.getLogger(__name__)


class StripeService:
    """Handles Stripe subscription payments"""
    
    def __init__(self):
        stripe.api_key = settings.stripe_secret_key
    
    async def create_customer(self, email: str, user_id: str) -> str:
        """Create a Stripe customer"""
        customer = stripe.Customer.create(
            email=email,
            metadata={"user_id": user_id}
        )
        return customer.id
    
    async def create_checkout_session(
        self,
        customer_id: str,
        return_url: str,
        user_id: str
    ) -> Tuple[str, str]:
        """
        Create an embedded Stripe Checkout session for subscription.
        return_url must include the literal {CHECKOUT_SESSION_ID} (Stripe replaces it after payment).
        Returns: (session_id, client_secret)
        """
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            ui_mode="embedded",
            return_url=return_url,
            line_items=[
                {
                    "price": settings.stripe_price_id,
                    "quantity": 1,
                }
            ],
            metadata={"user_id": user_id},
            subscription_data={
                "metadata": {"user_id": user_id}
            },
        )
        client_secret = getattr(session, "client_secret", None) or ""
        if not client_secret:
            raise RuntimeError("Stripe did not return client_secret for embedded checkout session")
        return session.id, client_secret
    
    async def get_subscription(self, subscription_id: str) -> Optional[dict]:
        """Get subscription details"""
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return {
                "id": subscription.id,
                "status": subscription.status,
                "current_period_start": datetime.fromtimestamp(subscription.current_period_start),
                "current_period_end": datetime.fromtimestamp(subscription.current_period_end),
                "cancel_at_period_end": subscription.cancel_at_period_end
            }
        except stripe.error.StripeError:
            return None
    
    async def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> bool:
        """Cancel a subscription"""
        try:
            if at_period_end:
                stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True
                )
            else:
                stripe.Subscription.delete(subscription_id)
            return True
        except stripe.error.StripeError:
            return False
    
    async def resume_subscription(self, subscription_id: str) -> bool:
        """Resume a canceled subscription (if still in period)"""
        try:
            stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=False
            )
            return True
        except stripe.error.StripeError:
            return False
    
    def construct_webhook_event(self, payload: bytes, sig_header: str) -> stripe.Event:
        """Construct and verify webhook event"""
        return stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.stripe_webhook_secret
        )
    
    def _resolve_tier_from_session(self, session) -> str:
        """Determine subscription tier (basic/premium) from a checkout session's line items."""
        basic_id = (settings.stripe_basic_price_id or "").strip()
        premium_id = (settings.stripe_premium_price_id or "").strip()

        try:
            line_items = stripe.checkout.Session.list_line_items(session.id, limit=5)
            for item in line_items.data:
                price_id = getattr(item.price, "id", None) if item.price else None
                if not price_id:
                    continue
                if basic_id and price_id == basic_id:
                    return "basic"
                if premium_id and price_id == premium_id:
                    return "premium"
                product_id = getattr(item.price, "product", None)
                if product_id:
                    product = stripe.Product.retrieve(product_id)
                    name = (product.name or "").lower()
                    if "premium" in name or "chad" == name.strip():
                        return "premium"
                    if "basic" in name or "chadlite" in name:
                        return "basic"
        except Exception as e:
            logger.warning("Could not resolve tier from checkout session line items: %s", e)

        # Fallback: use metadata or default to premium
        tier_meta = (getattr(session, "metadata", None) or {}).get("tier", "").lower()
        if tier_meta in ("basic", "premium"):
            return tier_meta
        return "premium"

    async def handle_webhook_event(self, event: stripe.Event) -> dict:
        """
        Process Stripe webhook events.
        Returns dict with user_id, subscription status updates, and resolved tier.
        """
        event_type = event.type
        data = event.data.object
        
        result = {
            "event_type": event_type,
            "user_id": None,
            "subscription_id": None,
            "status": None,
            "action": None,
            "tier": None,
        }
        
        if event_type == "checkout.session.completed":
            result["user_id"] = data.metadata.get("user_id")
            result["subscription_id"] = data.subscription
            result["action"] = "activate"
            result["tier"] = self._resolve_tier_from_session(data)
            
        elif event_type == "customer.subscription.created":
            result["user_id"] = data.metadata.get("user_id")
            result["subscription_id"] = data.id
            result["status"] = data.status
            result["action"] = "create"
            
        elif event_type == "customer.subscription.updated":
            result["user_id"] = data.metadata.get("user_id")
            result["subscription_id"] = data.id
            result["status"] = data.status
            result["action"] = "update"
            
        elif event_type == "customer.subscription.deleted":
            result["user_id"] = data.metadata.get("user_id")
            result["subscription_id"] = data.id
            result["status"] = "canceled"
            result["action"] = "cancel"
            
        elif event_type == "invoice.payment_succeeded":
            result["subscription_id"] = data.subscription
            result["action"] = "payment_success"
            
        elif event_type == "invoice.payment_failed":
            result["subscription_id"] = data.subscription
            result["action"] = "payment_failed"
        
        return result


# Singleton instance
stripe_service = StripeService()
