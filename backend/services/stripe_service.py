"""
Stripe Service - Subscription-based payments
"""

import stripe
from typing import Optional, Tuple
from datetime import datetime
from config import settings


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
    
    async def handle_webhook_event(self, event: stripe.Event) -> dict:
        """
        Process Stripe webhook events
        Returns dict with user_id and subscription status updates
        """
        event_type = event.type
        data = event.data.object
        
        result = {
            "event_type": event_type,
            "user_id": None,
            "subscription_id": None,
            "status": None,
            "action": None
        }
        
        if event_type == "checkout.session.completed":
            result["user_id"] = data.metadata.get("user_id")
            result["subscription_id"] = data.subscription
            result["action"] = "activate"
            
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
