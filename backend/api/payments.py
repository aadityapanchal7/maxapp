"""
Payments API — Stripe SetupIntent + Subscription flow, Apple IAP (iOS) verify + ASN V2.
"""

import logging
import stripe
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Depends
from uuid import UUID
from pydantic import BaseModel
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sa_update
from db import get_db
from middleware import get_current_user
from middleware.rate_limit import rate_limit
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
from models.sqlalchemy_models import User, Scan, Creator, CreatorSubscription
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])

# Apple-native billing ONLY (2026-07): there are no Stripe subscriptions and
# none may ever be created. Every Stripe subscription endpoint (create +
# manage) is retired below with 410 Gone. The Stripe webhook and /status stay
# mounted as read-only safety nets, but nothing can mint a Stripe sub anymore.
STRIPE_BILLING_RETIRED = True


def _reject_stripe_retired() -> None:
    if STRIPE_BILLING_RETIRED:
        raise HTTPException(
            status_code=410,
            detail="Card billing is retired — subscribe through the App Store.",
        )


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
    subscription_status: str = "active",
):
    """Shared activation logic for webhook + test-activate (+ referral comp).

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
    user.subscription_status = subscription_status
    # Chad Lite is RETIRED (single-plan pivot, 2026-07): every activation —
    # regardless of provider, price, or metadata — grants Chad. Legacy Lite
    # subscribers keep their old price but get the full feature set. This is
    # the single choke point, so no webhook replay can re-downgrade anyone.
    if subscription_tier in ("basic", "premium"):
        user.subscription_tier = "premium"
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
    # Bulk UPDATE instead of loading every scan row into the session to flip a
    # single boolean — one statement, no per-row materialization.
    await db.execute(
        sa_update(Scan).where(Scan.user_id == user_uuid).values(is_unlocked=True)
    )
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


async def _resolve_apple_user(claims: dict, db: AsyncSession) -> Optional[str]:
    """Resolve the owning user from TRUSTED Apple transaction claims.

    Never trusts the raw notification's inner JWS: this is called only on claims
    fetched from Apple's authenticated App Store Server API.

    Resolution order matters: the CURRENT holder of the subscription (stored
    subscription_id == originalTransactionId) wins over the appAccountToken.
    The token is frozen at purchase time forever, so after a legitimate
    cross-account adoption/transfer it still names the ORIGINAL buying account —
    resolving by token first made every renewal snap the entitlement back to
    the old account, silently reverting the transfer each billing cycle.
    """
    original = str(claims.get("originalTransactionId") or "")
    if original:
        res = await db.execute(select(User).where(User.subscription_id == original))
        row = res.scalar_one_or_none()
        if row:
            return str(row.id)
    tok = claims.get("appAccountToken")
    if tok:
        try:
            UUID(str(tok))
            return str(tok)
        except ValueError:
            pass
    return None


async def _assert_claimable(user_id: str, claims: dict, db: AsyncSession) -> None:
    """Guard the appAccountToken mismatch case WITHOUT stranding real customers.

    An Apple subscription belongs to an APPLE ID, not to the app account that
    happened to buy it — so a user on a new phone / reinstall / fresh signup
    legitimately presents a transaction stamped with an older app-account token.
    Hard-rejecting that (the old behavior) locked paying users out of the app
    forever, since the client can only ever replay the same transaction.

    Policy: a mismatched token is fine as long as NO OTHER account currently
    holds this subscription. If someone else actively holds it, refuse — that's
    the case the original guard existed for (a replayed/stolen transaction id
    must never take an entitlement away from its active owner).
    """
    from services import apple_iap_service as apple

    if apple.account_token_matches(claims, user_id) is not False:
        return  # matches, or a legacy transaction with no token

    original = str(claims.get("originalTransactionId") or "")
    holder = None
    if original:
        holder = (await db.execute(
            select(User).where(User.subscription_id == original)
        )).scalars().first()

    if holder is not None and str(holder.id) != str(user_id):
        logger.warning(
            "Apple IAP: token mismatch AND actively held by another account "
            "(txn=%s holder=%s caller=%s) — refusing", original, holder.id, user_id,
        )
        raise ValueError("account_token_mismatch")

    logger.info(
        "Apple IAP: adopting unclaimed subscription across app accounts "
        "(txn=%s token=%s caller=%s)", original, claims.get("appAccountToken"), user_id,
    )


async def _apple_sync_entitlement(user_id: str, claims: dict, db: AsyncSession) -> None:
    """Apply App Store transaction claims to Supabase user (active or expired)."""
    from services import apple_iap_service as apple

    tier = apple.tier_for_product_id(claims.get("productId") or "")
    if not tier:
        raise ValueError("unknown_product")
    original = str(claims.get("originalTransactionId") or "")
    if not original:
        raise ValueError("missing_original")
    await _assert_claimable(user_id, claims, db)
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


def _stripe_field(sub, key):
    """Read a field from a Stripe subscription object (attr) or dict."""
    if sub is None:
        return None
    if isinstance(sub, dict):
        return sub.get(key)
    return getattr(sub, key, None)


async def _sync_subscription_tier_from_stripe(user_id: str, subscription_id: str, db: AsyncSession) -> None:
    try:
        sub = stripe_service.retrieve_subscription_object(subscription_id)
        tier = stripe_service.tier_from_subscription(sub)
        # Persist the period end so the entitlement date-guard
        # (auth_middleware._subscription_expired) and the reconciliation job also
        # protect Stripe users: a failed renewal (is_paid left True) then expires
        # once current_period_end passes, instead of granting access forever.
        cpe = _stripe_field(sub, "current_period_end")
        user = await db.get(User, UUID(user_id))
        if user:
            if tier:
                user.subscription_tier = tier
            if cpe:
                try:
                    user.subscription_end_date = datetime.fromtimestamp(int(cpe), tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    pass
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
    _reject_stripe_retired()
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

@router.post(
    "/subscribe",
    response_model=SubscribeResponse,
    dependencies=[Depends(rate_limit(limit=10, window_s=300, scope="subscribe"))],
)
async def subscribe(
    body: SubscribeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    After the client confirms a SetupIntent, call this to create the
    weekly Subscription on the saved payment method.
    """
    _reject_stripe_retired()
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
    _reject_stripe_retired()

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
    # This endpoint is unauthenticated (signature is only verified AFTER the
    # full body is buffered). Real Stripe events are small and always carry
    # Content-Length; reject anything oversized/chunked before buffering it.
    _cl = request.headers.get("content-length")
    if _cl is None or not _cl.isdigit() or int(_cl) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload too large")
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe_service.construct_webhook_event(payload, sig_header)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {e}")

    # Marketplace purchases (per-item Checkout) carry marketplace_item_id in
    # metadata and are fulfilled as purchases + entitlements - NOT as legacy
    # account-tier activations.
    if event.type == "checkout.session.completed":
        meta = dict(getattr(event.data.object, "metadata", {}) or {})
        mk_item = meta.get("marketplace_item_id")
        mk_uid = meta.get("user_id")
        if mk_item and mk_uid:
            from api.marketplace import fulfill_marketplace_purchase
            sub_ref = getattr(event.data.object, "subscription", None)
            await fulfill_marketplace_purchase(
                db, mk_uid, mk_item, "stripe",
                str(sub_ref) if sub_ref else str(getattr(event.data.object, "id", "")),
            )
            return {"status": "ok", "fulfilled": mk_item}

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


@router.post(
    "/apple/verify",
    dependencies=[Depends(rate_limit(limit=20, window_s=300, scope="apple_verify"))],
)
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

    logger.info(
        "Apple IAP verify: user=%s tid=%s product_id=%s configured=%s",
        current_user["id"], tid, body.product_id, apple.apple_iap_configured(),
    )

    server_verified = False
    if apple.apple_iap_configured():
        try:
            claims = await apple.fetch_transaction_claims(tid)
            apple.validate_claims_for_user(claims, current_user["id"])

            logger.info(
                "Apple IAP claims: user=%s tid=%s productId=%s expiresDate=%s environment=%s bundleId=%s",
                current_user["id"],
                tid,
                claims.get("productId"),
                claims.get("expiresDate"),
                claims.get("environment"),
                claims.get("bundleId"),
            )

            if not apple.subscription_active_from_claims(claims):
                exp = apple.expires_datetime_from_claims(claims)
                logger.info(
                    "Apple IAP expired (stale queued transaction, acking to clear client queue): "
                    "user=%s tid=%s expiresDate=%s (utc now=%s)",
                    current_user["id"], tid, exp, datetime.utcnow(),
                )
                # Historical/expired transactions are NOT an error — StoreKit
                # replays old unfinished transactions on every launch. Return
                # 200 so the client calls finishTransaction and clears the
                # queue. Keep user's current entitlement state untouched
                # (do not deactivate based on a stale transaction id).
                return {
                    "status": "expired",
                    "tier": apple.tier_for_product_id(claims.get("productId") or ""),
                    "message": "Transaction expired; acknowledged.",
                }

            try:
                await _apple_sync_entitlement(str(current_user["id"]), claims, db)
            except ValueError as e:
                logger.warning(
                    "Apple IAP entitlement sync failed: user=%s tid=%s err=%s",
                    current_user["id"], tid, e,
                )
                raise HTTPException(status_code=400, detail=str(e))

            tier = apple.tier_for_product_id(claims.get("productId") or "")
            logger.info("Apple IAP verified OK: user=%s tid=%s tier=%s", current_user["id"], tid, tier)
            return {"status": "ok", "tier": tier}
        except HTTPException:
            raise
        except ValueError as e:
            logger.warning(
                "Apple IAP ValueError (server verify): user=%s tid=%s err=%s",
                current_user["id"], tid, e,
            )
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.warning(
                "Apple Server API verification failed for user %s, falling back to client-trust: %s",
                current_user["id"], e,
            )

    if not server_verified:
        # SECURITY: never trust a client-reported product_id in production — that
        # would let anyone POST {transaction_id, product_id:"premium"} and unlock
        # paid features for free. The client-trust path exists ONLY as a dev
        # convenience before the App Store Server API keys are wired up.
        # Use settings.is_production (also true on Render / PRODUCTION env), not a
        # bare app_env check — else a deploy missing APP_ENV=production would let a
        # client POST {transaction_id, product_id:"premium"} and self-grant premium.
        if settings.is_production:
            logger.error(
                "Apple IAP could not be server-verified in production "
                "(configured=%s) — refusing client-trust activation: user=%s tid=%s",
                apple.apple_iap_configured(), current_user["id"], tid,
            )
            raise HTTPException(
                status_code=503,
                detail="Could not verify your purchase right now. Please try again shortly.",
            )

        logger.info("Using client-trust fallback for Apple IAP user %s (non-production)", current_user["id"])
        client_pid = (body.product_id or "").strip()
        tier = apple.tier_for_product_id(client_pid) if client_pid else None
        if not tier:
            # Single-plan pivot: everything grants Chad (premium) now.
            tier = "premium"

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
    token = request.query_params.get("token") or request.query_params.get("secret")
    # Whether THIS request is provably from Apple. Two independent trust anchors:
    #   (a) the shared-secret token in the URL (only Apple + us know it), and
    #   (b) — applied in the grant path below — a round-trip to Apple's
    #       authenticated App Store Server API to fetch the real transaction.
    # Entitlements are only ever granted when one of these vouches for the data;
    # the raw inner JWS is NEVER trusted on its own (it isn't signature-verified).
    authenticated_via_secret = False
    if sec:
        if token != sec:
            raise HTTPException(status_code=403, detail="Invalid notification token")
        authenticated_via_secret = True
    elif settings.is_production and not apple.apple_iap_configured():
        # No shared secret AND no App Store Server API key configured: we can
        # neither authenticate the caller nor independently verify the
        # transaction with Apple. Fail closed (like the Sendblue webhook) so a
        # forged notification can't mint a free premium subscription.
        raise HTTPException(status_code=403, detail="Webhook not configured")

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

    # Route per-creator subscription products to the creator entitlement path —
    # they must NEVER touch the base Chad subscription (_activate/_deactivate_user).
    product_id = str(txn_inner.get("productId") or "")
    if product_id.startswith("com.cannon.creator."):
        try:
            await _handle_creator_asn(
                ntype=ntype, product_id=product_id, user_id=user_id_str,
                txn_id=txn_id, original_id=original_id, txn_inner=txn_inner,
                authenticated_via_secret=authenticated_via_secret, db=db,
            )
        except Exception:
            logger.exception("creator ASN handler error")
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
            granted = False
            # Preferred path: re-fetch the transaction from Apple's authenticated
            # App Store Server API. This is the strong trust anchor — a forged
            # transactionId returns 404, so nothing is granted. Resolve and
            # validate the owner from the TRUSTED claims, never from the
            # attacker-controllable inner JWS's appAccountToken.
            if txn_id and apple.apple_iap_configured():
                try:
                    claims = await apple.fetch_transaction_claims(txn_id)
                    trusted_uid = await _resolve_apple_user(claims, db) or user_id_str
                    apple.validate_claims_for_user(claims, trusted_uid)
                    await _apple_sync_entitlement(trusted_uid, claims, db)
                    granted = True
                except Exception as e:
                    logger.warning("ASN trusted entitlement sync failed: %s", e)
            # Fallback ONLY when the request itself is authenticated as Apple via
            # the shared-secret URL — then the inner JWS came from Apple and can
            # be trusted without the Server API round-trip. Otherwise grant
            # nothing: the raw JWS is not signature-verified.
            if not granted and authenticated_via_secret:
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


async def _handle_creator_asn(
    *, ntype: str, product_id: str, user_id: str, txn_id: Optional[str],
    original_id: str, txn_inner: dict, authenticated_via_secret: bool, db: AsyncSession,
) -> None:
    """ASN lifecycle for a per-creator subscription product. Resolves the creator
    by its Apple product id and activates/deactivates the creator sub only."""
    from services import apple_iap_service as apple
    from services import creator_service

    creator = (await db.execute(
        select(Creator).where(Creator.apple_product_id == product_id)
    )).scalar_one_or_none()
    if creator is None:
        logger.info("creator ASN: no creator for product %s", product_id)
        return

    if ntype in ("REFUND", "REVOKE", "EXPIRED"):
        await creator_service.deactivate_creator_subscription(
            user_id=user_id, creator=creator, db=db, status="expired",
        )
        await db.commit()
        return

    if ntype in ("SUBSCRIBED", "DID_RENEW", "INITIAL_BUY",
                 "DID_CHANGE_RENEWAL_PREF", "DID_CHANGE_RENEWAL_STATUS"):
        expires = None
        claims = None
        if txn_id and apple.apple_iap_configured():
            try:
                claims = await apple.fetch_transaction_claims(txn_id)
                apple.validate_claims_for_user(claims, user_id)
            except Exception as e:
                logger.warning("creator ASN trusted fetch failed: %s", e)
                claims = None
        if claims is None and authenticated_via_secret:
            claims = txn_inner  # inner JWS trusted only when request carried the shared secret
        if claims is None:
            return  # not verifiable — grant nothing
        if not apple.subscription_active_from_claims(claims):
            await creator_service.deactivate_creator_subscription(
                user_id=user_id, creator=creator, db=db, status="expired",
            )
            await db.commit()
            return
        expires = apple.expires_datetime_from_claims(claims)
        await creator_service.activate_creator_subscription(
            user_id=user_id, creator=creator, product_id=product_id,
            original_transaction_id=original_id or txn_id, provider="apple",
            expires_at=expires, db=db,
            # Renewal-preference notifications must not overwrite a user's
            # auto-renew-OFF choice; only true (re)subscribes force it on.
            auto_renew=(True if ntype in ("SUBSCRIBED", "DID_RENEW", "INITIAL_BUY") else None),
        )
        await db.commit()
        # Entitlement committed — put the creator's habits on their schedule
        # (idempotent: renewals no-op because an active schedule already exists).
        await creator_service.ensure_creator_schedule(user_id, creator.maxx_id, db)
        return

    if ntype == "DID_FAIL_TO_RENEW":
        sub = (await db.execute(
            select(CreatorSubscription).where(
                (CreatorSubscription.user_id == UUID(user_id))
                & (CreatorSubscription.creator_id == creator.id)
            )
        )).scalar_one_or_none()
        if sub is not None:
            sub.status = "past_due"
            await db.commit()


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
    _reject_stripe_retired()

    sub_id = current_user.get("subscription_id")
    if not sub_id:
        raise HTTPException(status_code=404, detail="No active subscription")

    # Chad Lite is RETIRED (single-plan pivot, 2026-07): the only valid tier is
    # premium. Nobody can switch INTO the legacy plan; existing Lite subscribers
    # are grandfathered at their old price with full Chad access.
    if body.tier != "premium":
        raise HTTPException(status_code=400, detail="Chad Lite is retired — Chad is the only plan.")

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
    _reject_stripe_retired()

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

@router.post(
    "/create-session",
    response_model=CheckoutSessionResponse,
    dependencies=[Depends(rate_limit(limit=10, window_s=300, scope="create_session"))],
)
async def create_checkout_session(
    data: PaymentCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _reject_stripe_retired()
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


@router.post(
    "/test-activate",
    dependencies=[Depends(rate_limit(limit=10, window_s=300, scope="test_activate"))],
)
async def test_activate_subscription(
    body: TestActivateBody = TestActivateBody(),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from config import settings as _s
    # Block in production via the authoritative is_production (matches
    # auth.py's _block_in_production). No `debug` escape hatch — a stray
    # DEBUG=true in prod must not reopen this premium-minting endpoint.
    if _s.is_production:
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
