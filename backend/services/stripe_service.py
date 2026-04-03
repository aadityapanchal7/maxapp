"""
Stripe Service — SetupIntent + Subscription-based payments
"""

import logging
import stripe
from typing import Optional, Tuple
from datetime import datetime
from config import settings

logger = logging.getLogger(__name__)

TIER_PRICE_MAP = {
    "basic": lambda: settings.stripe_price_id_weekly_basic,
    "premium": lambda: settings.stripe_price_id_weekly_premium,
}


class StripeService:
    """Handles Stripe subscription payments via SetupIntent → Subscription flow."""

    def __init__(self):
        stripe.api_key = settings.stripe_secret_key

    # ------------------------------------------------------------------
    # Customer
    # ------------------------------------------------------------------

    async def create_customer(self, email: str, user_id: str) -> str:
        customer = stripe.Customer.create(
            email=email,
            metadata={"user_id": user_id},
        )
        return customer.id

    # ------------------------------------------------------------------
    # Ephemeral Key (required by Payment Sheet on mobile)
    # ------------------------------------------------------------------

    async def create_ephemeral_key(self, customer_id: str) -> str:
        """Return the raw JSON-string secret for Payment Sheet initialisation."""
        key = stripe.EphemeralKey.create(
            customer=customer_id,
            stripe_version=settings.stripe_ephemeral_key_api_version,
        )
        return key.secret

    # ------------------------------------------------------------------
    # SetupIntent — save card / Apple Pay for later
    # ------------------------------------------------------------------

    async def create_setup_intent(self, customer_id: str, user_id: str) -> Tuple[str, str]:
        """Returns (setup_intent_id, client_secret)."""
        si = stripe.SetupIntent.create(
            customer=customer_id,
            automatic_payment_methods={"enabled": True},
            metadata={"user_id": user_id},
        )
        return si.id, si.client_secret

    async def get_setup_intent(self, setup_intent_id: str) -> stripe.SetupIntent:
        return stripe.SetupIntent.retrieve(setup_intent_id)

    # ------------------------------------------------------------------
    # Subscription — create weekly sub on saved payment method
    # ------------------------------------------------------------------

    def resolve_price_id(self, tier: str) -> str:
        getter = TIER_PRICE_MAP.get(tier)
        if not getter:
            raise ValueError(f"Unknown tier: {tier}")
        price_id = getter()
        if not price_id:
            raise ValueError(
                f"STRIPE_PRICE_ID_WEEKLY_{tier.upper()} is not set. "
                "Create a recurring weekly Price in Stripe Dashboard and add the ID to .env."
            )
        return price_id

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        payment_method_id: str,
        user_id: str,
    ) -> stripe.Subscription:
        stripe.Customer.modify(
            customer_id,
            invoice_settings={"default_payment_method": payment_method_id},
        )
        sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price_id}],
            default_payment_method=payment_method_id,
            metadata={"user_id": user_id},
            expand=["latest_invoice"],
        )
        return sub

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    async def get_subscription(self, subscription_id: str) -> Optional[dict]:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return {
                "id": subscription.id,
                "status": subscription.status,
                "current_period_start": datetime.fromtimestamp(subscription.current_period_start),
                "current_period_end": datetime.fromtimestamp(subscription.current_period_end),
                "cancel_at_period_end": subscription.cancel_at_period_end,
            }
        except stripe.error.StripeError:
            return None

    async def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> bool:
        try:
            if at_period_end:
                stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
            else:
                stripe.Subscription.delete(subscription_id)
            return True
        except stripe.error.StripeError:
            return False

    async def resume_subscription(self, subscription_id: str) -> bool:
        try:
            stripe.Subscription.modify(subscription_id, cancel_at_period_end=False)
            return True
        except stripe.error.StripeError:
            return False

    # ------------------------------------------------------------------
    # Legacy: embedded Checkout session (kept for backward compat)
    # ------------------------------------------------------------------

    async def create_checkout_session(
        self,
        customer_id: str,
        return_url: str,
        user_id: str,
    ) -> Tuple[str, str]:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            ui_mode="embedded",
            return_url=return_url,
            line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
            metadata={"user_id": user_id},
            subscription_data={"metadata": {"user_id": user_id}},
        )
        client_secret = getattr(session, "client_secret", None) or ""
        if not client_secret:
            raise RuntimeError("Stripe did not return client_secret for embedded checkout session")
        return session.id, client_secret

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> stripe.Event:
        return stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.stripe_webhook_secret,
        )

    async def _resolve_user_id(self, data) -> Optional[str]:
        """Best-effort user_id resolution: metadata → Customer metadata fallback."""
        uid = getattr(data, "metadata", {}).get("user_id") if hasattr(data, "metadata") else None
        if uid:
            return uid
        customer_id = getattr(data, "customer", None)
        if customer_id:
            try:
                cust = stripe.Customer.retrieve(customer_id)
                return (cust.metadata or {}).get("user_id")
            except stripe.error.StripeError:
                pass
        return None

    async def handle_webhook_event(self, event: stripe.Event) -> dict:
        event_type = event.type
        data = event.data.object

        result = {
            "event_type": event_type,
            "user_id": None,
            "subscription_id": None,
            "status": None,
            "action": None,
        }

        if event_type == "checkout.session.completed":
            result["user_id"] = (data.metadata or {}).get("user_id")
            result["subscription_id"] = data.subscription
            result["action"] = "activate"

        elif event_type == "customer.subscription.created":
            result["user_id"] = await self._resolve_user_id(data)
            result["subscription_id"] = data.id
            result["status"] = data.status
            result["action"] = "activate" if data.status == "active" else "create"

        elif event_type == "customer.subscription.updated":
            result["user_id"] = await self._resolve_user_id(data)
            result["subscription_id"] = data.id
            result["status"] = data.status
            if data.status == "active":
                result["action"] = "activate"
            elif data.status in ("past_due", "unpaid"):
                result["action"] = "payment_failed"
            else:
                result["action"] = "update"

        elif event_type == "customer.subscription.deleted":
            result["user_id"] = await self._resolve_user_id(data)
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


stripe_service = StripeService()
