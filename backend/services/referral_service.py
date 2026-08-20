"""Referral / promo code logic (RALPH_REFERRAL Phases 2-4, 6).

Server-authoritative, atomic, one-per-user, audited. The API layer
(`api/referral.py`) is a thin wrapper over `validate_code` (pure read) and
`redeem_code` (the transactional grant). Entitlement is granted ONLY here via
the shared `_activate_user` path — the client never self-grants.

Compliance (encoded, not optional):
  * free_comp / 100%-off  -> server grants entitlement, route past the paywall.
  * discount on iOS       -> Apple Offer Code only (we surface the offer id;
                             we NEVER charge a cheaper price via the backend).
  * discount on web       -> Stripe promotion_code / coupon / price_id.
  * discounts are behind `referral_discounts_enabled` and are INERT (recognized,
    "discount coming") when the flag is off or the platform ids are unset — they
    never charge a wrong amount.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.sqlalchemy_models import ReferralCode, ReferralRedemption, User

logger = logging.getLogger(__name__)

_CODE_RE = re.compile(r"[^A-Z0-9]")


class ReferralError(Exception):
    """A redemption/validation failure with a stable machine `reason`."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def normalize_code(code: object) -> str:
    """Case-insensitive canonical form: uppercased, A-Z0-9 only."""
    return _CODE_RE.sub("", str(code or "").strip().upper())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def window_state(row: ReferralCode, now: Optional[datetime] = None) -> Optional[str]:
    """Pure check of a code's lifecycle window. Returns a failure `reason` or
    None if the code is currently live. (Does not check per-user limits.)"""
    now = now or _utcnow()
    if not row.is_active:
        return "inactive"
    starts = _as_aware(row.starts_at)
    expires = _as_aware(row.expires_at)
    if starts and now < starts:
        return "not_started"
    if expires and now >= expires:
        return "expired"
    if row.max_redemptions is not None and (row.redemption_count or 0) >= row.max_redemptions:
        return "max_reached"
    return None


_REASON_MESSAGE = {
    "not_found": "that code isn't valid.",
    "inactive": "that code is no longer active.",
    "not_started": "that code isn't active yet.",
    "expired": "that code has expired.",
    "max_reached": "that code has been fully claimed.",
    "already_used": "you've already used this code.",
    "self_referral": "you can't redeem your own code.",
    "already_entitled": "you're already subscribed, so there's nothing to redeem.",
    "disabled": "referral codes aren't available right now.",
    "discount_unavailable": "code recognized, the discount is coming soon.",
}


def _discount_payload(row: ReferralCode) -> Optional[dict]:
    """Display-only discount descriptor (never a price the backend invents)."""
    if row.kind != "discount":
        return None
    kind = row.discount_kind
    val = float(row.discount_value) if row.discount_value is not None else None
    if kind == "percent" and val is not None:
        label = f"{int(val) if val == int(val) else val}% off"
    elif kind == "fixed" and val is not None:
        label = f"${int(val) if val == int(val) else val} off"
    else:
        label = "discount"
    return {"kind": kind, "value": val, "label": label}


async def _load_code(db: AsyncSession, code: str) -> Optional[ReferralCode]:
    norm = normalize_code(code)
    if not norm:
        return None
    return (
        await db.execute(select(ReferralCode).where(ReferralCode.code == norm))
    ).scalar_one_or_none()


async def _existing_redemption(db: AsyncSession, code_id: UUID, user_id: UUID) -> Optional[ReferralRedemption]:
    return (
        await db.execute(
            select(ReferralRedemption).where(
                ReferralRedemption.code_id == code_id,
                ReferralRedemption.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def validate_code(db: AsyncSession, code: str, user_id: Optional[str] = None) -> dict:
    """Pure read: is this code currently redeemable? No side effects.
    Shape: {valid, kind, free, discount, message, reason}."""
    row = await _load_code(db, code)
    if row is None:
        return {"valid": False, "reason": "not_found", "message": _REASON_MESSAGE["not_found"]}

    reason = window_state(row)
    if reason:
        return {"valid": False, "kind": row.kind, "reason": reason, "message": _REASON_MESSAGE.get(reason, "that code can't be used.")}

    if user_id:
        uid = UUID(str(user_id))
        if row.owner_user_id and row.owner_user_id == uid:
            return {"valid": False, "kind": row.kind, "reason": "self_referral", "message": _REASON_MESSAGE["self_referral"]}
        # Built-in launch comps (CASH99) are re-redeemable: each redemption
        # grants a fresh 1-week window, so a prior use never invalidates entry.
        if not _is_default_comp(row) and await _existing_redemption(db, row.id, uid):
            return {"valid": False, "kind": row.kind, "reason": "already_used", "message": _REASON_MESSAGE["already_used"]}

    free = row.kind == "free_comp" or (
        row.kind == "discount" and row.discount_kind == "percent"
        and row.discount_value is not None and float(row.discount_value) >= 100
    )
    discount = None if free else _discount_payload(row)
    if free:
        msg = "code applied, premium is on us."
    elif discount:
        msg = f"code applied, {discount['label']}."
    else:
        msg = "code applied."
    return {"valid": True, "kind": row.kind, "free": free, "discount": discount, "message": msg, "reason": None}


def _is_default_comp(row: ReferralCode) -> bool:
    """Built-in launch comp (e.g. CASH99): re-redeemable, each grant = 1 week."""
    return row.code in {normalize_code(c) for c in DEFAULT_COMP_CODES}


def _is_full_comp(row: ReferralCode) -> bool:
    if row.kind == "free_comp":
        return True
    return (
        row.kind == "discount" and row.discount_kind == "percent"
        and row.discount_value is not None and float(row.discount_value) >= 100
    )


async def redeem_code(db: AsyncSession, user: User, code: str, platform: Optional[str]) -> dict:
    """Atomically redeem `code` for `user`. Raises ReferralError on any rule
    failure. Returns {result, free, kind, discount, redemption_id, message,
    apple_offer_code?, stripe_promotion_code?}."""
    if not getattr(settings, "referrals_enabled", False):
        raise ReferralError("disabled", _REASON_MESSAGE["disabled"])

    row = await _load_code(db, code)
    if row is None:
        raise ReferralError("not_found", _REASON_MESSAGE["not_found"])

    reason = window_state(row)
    if reason:
        raise ReferralError(reason, _REASON_MESSAGE.get(reason, "that code can't be used."))

    uid = user.id if isinstance(user.id, UUID) else UUID(str(user.id))
    if row.owner_user_id and row.owner_user_id == uid:
        raise ReferralError("self_referral", _REASON_MESSAGE["self_referral"])

    # Idempotency / one-per-user (fast path before any mutation). Built-in
    # launch comps (CASH99) are exempt: they're re-redeemable, each redemption
    # granting a fresh 1-week window.
    default_comp = _is_default_comp(row)
    existing = await _existing_redemption(db, row.id, uid)
    if existing and not default_comp:
        return _result_payload(row, existing.result, existing.id, platform, idempotent=True)

    full_comp = _is_full_comp(row)
    # Don't comp over a CURRENTLY-ACTIVE store subscription — a comp overwrites
    # the subscription fields, which must never stomp a live Apple/Stripe plan.
    # An EXPIRED subscriber (store or comp) and an active comp holder may both
    # redeem: is_paid alone stays True after expiry, so the old blanket
    # `is_paid` check wrongly locked out exactly the users a comp is for.
    if full_comp:
        end = _as_aware(user.subscription_end_date)
        currently_entitled = bool(user.is_paid) and (end is None or end > datetime.now(timezone.utc))
        via_comp = (user.billing_provider or "") == "referral_comp"
        if currently_entitled and not via_comp:
            raise ReferralError("already_entitled", _REASON_MESSAGE["already_entitled"])

    # Decide the audited result up front.
    if full_comp:
        result = "comped"
    elif row.kind == "discount":
        result = "discount_applied"
    else:
        result = "attributed"

    # 1) Atomic, concurrency-safe count guard (only consume a slot when within max).
    incr = await db.execute(
        text(
            "UPDATE referral_codes SET redemption_count = redemption_count + 1, updated_at = now() "
            "WHERE id = :id AND is_active = TRUE "
            "AND (max_redemptions IS NULL OR redemption_count < max_redemptions) "
            "RETURNING redemption_count"
        ),
        {"id": str(row.id)},
    )
    if incr.fetchone() is None:
        await db.rollback()
        raise ReferralError("max_reached", _REASON_MESSAGE["max_reached"])

    # 2) Audit row. The unique (code_id, user_id) is the one-per-user gate for
    #    normal codes, even under a race that beat the fast-path check. For a
    #    re-redeemable default comp, REUSE the existing row (unique constraint
    #    forbids a second) — the re-grant itself is the effect that matters.
    if existing and default_comp:
        redemption = existing
        redemption.result = result
        redemption.platform = platform
        redemption.kind_at_redemption = row.kind
    else:
        redemption = ReferralRedemption(
            code_id=row.id, user_id=uid, kind_at_redemption=row.kind,
            result=result, platform=platform,
        )
        db.add(redemption)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            existing = await _existing_redemption(db, row.id, uid)
            if existing:
                if default_comp:
                    # Race with our own first redemption — reuse and re-grant.
                    redemption = existing
                else:
                    return _result_payload(row, existing.result, existing.id, platform, idempotent=True)
            else:
                raise ReferralError("already_used", _REASON_MESSAGE["already_used"])

    # 3) Apply the effect.
    if full_comp:
        from api.payments import _activate_user
        # Comp duration: the built-in launch codes (e.g. CASH99) are a 1-WEEK
        # free trial, not a lifetime grant — time-box to 7 days from redemption.
        # A code's own expires_at still wins when it's sooner. Other free_comp
        # codes keep their existing semantics (expires_at or unlimited).
        comp_end = _as_aware(row.expires_at)
        if row.code in {normalize_code(c) for c in DEFAULT_COMP_CODES}:
            week_end = datetime.now(timezone.utc) + timedelta(days=DEFAULT_COMP_GRANT_DAYS)
            comp_end = min(comp_end, week_end) if comp_end else week_end
        await _activate_user(
            str(uid), None, db,
            subscription_tier=(row.granted_tier if row.granted_tier in ("basic", "premium") else "premium"),
            billing_provider="referral_comp",          # marks a comp (not stripe/apple)
            subscription_status="comped",
            subscription_end_date=comp_end,
        )

    # 4) Attribution (always), reward hook (flag-gated).
    db_user = await db.get(User, uid)
    if db_user is not None:
        db_user.referred_by_code_id = row.id
        db_user.referral_source = row.campaign or ("owner:" + str(row.owner_user_id) if row.owner_user_id else "code")
    await _maybe_reward_referrer(db, row, uid, result)

    await db.commit()
    logger.info("referral redeem code=%s user=%s result=%s", row.code, uid, result)
    return _result_payload(row, result, redemption.id, platform, idempotent=False)


async def _maybe_reward_referrer(db: AsyncSession, row: ReferralCode, redeemer_id: UUID, result: str) -> None:
    """Reward hook (RALPH_REFERRAL Phase 6) — flag-gated OFF. A clean seam:
    when a referee actually converts/comps and the code has an owner, extend the
    owner's entitlement. No-op unless `referral_rewards_enabled`."""
    if not getattr(settings, "referral_rewards_enabled", False):
        return
    if result not in ("comped", "discount_applied"):
        return
    if not row.owner_user_id or row.owner_user_id == redeemer_id:
        return
    try:
        owner = await db.get(User, row.owner_user_id)
        if owner is None:
            return
        from datetime import timedelta
        base = _as_aware(owner.subscription_end_date) or _utcnow()
        owner.subscription_end_date = max(base, _utcnow()) + timedelta(days=30)
        # Only MINT comp entitlement for a non-paying owner. If the owner is
        # already a real Stripe/Apple subscriber, extend their end date but leave
        # billing_provider/is_paid/status alone — otherwise we'd overwrite their
        # provider to 'referral_comp' and reconcile_expired_subscriptions (which
        # expires referral_comp/apple rows) could later revoke a paying customer.
        prov = (owner.billing_provider or "").lower()
        if prov not in ("stripe", "apple") and not owner.is_paid:
            owner.is_paid = True
            owner.billing_provider = "referral_comp"
            if not owner.subscription_tier or owner.subscription_tier == "free":
                owner.subscription_tier = "premium"
            owner.subscription_status = "comped"
    except Exception as e:  # never let a reward failure break the redemption
        logger.warning("referral reward hook skipped: %s", e)


def _result_payload(row: ReferralCode, result: str, redemption_id, platform: Optional[str], *, idempotent: bool) -> dict:
    free = result == "comped"
    payload: dict = {
        "result": result,
        "kind": row.kind,
        "free": free,
        "discount": None if free else _discount_payload(row),
        "redemption_id": str(redemption_id),
        "idempotent": idempotent,
        "message": ("premium is on us, welcome in." if free else "code applied."),
    }
    if result == "discount_applied":
        payload.update(_discount_redemption_targets(row, platform))
    return payload


def _discount_redemption_targets(row: ReferralCode, platform: Optional[str]) -> dict:
    """Platform-split discount targets (Phase 4). INERT + safe unless the flag is
    on AND the relevant platform id is set — otherwise 'discount coming', never a
    price. iOS = Apple Offer Code; web = Stripe promo/coupon/price."""
    enabled = getattr(settings, "referral_discounts_enabled", False)
    plat = (platform or "").lower()
    if not enabled:
        return {"discount_status": "coming_soon", "message": _REASON_MESSAGE["discount_unavailable"]}
    if plat == "ios":
        offer = row.apple_offer_code or row.apple_offer_id
        if not offer:
            return {"discount_status": "coming_soon", "message": _REASON_MESSAGE["discount_unavailable"]}
        # The client presents StoreKit's code-redemption sheet with this offer.
        return {"discount_status": "apple_offer", "apple_offer_code": row.apple_offer_code,
                "apple_offer_id": row.apple_offer_id, "message": "redeem this offer in the App Store sheet."}
    # web / stripe
    target = row.stripe_promotion_code or row.stripe_coupon_id or row.stripe_price_id
    if not target:
        return {"discount_status": "coming_soon", "message": _REASON_MESSAGE["discount_unavailable"]}
    return {"discount_status": "stripe",
            "stripe_promotion_code": row.stripe_promotion_code,
            "stripe_coupon_id": row.stripe_coupon_id,
            "stripe_price_id": row.stripe_price_id,
            "message": "discount will apply at checkout."}


# Built-in launch comp codes — full free-premium, server-granted. Seeded
# idempotently on startup so they exist in every environment without an ops
# step (and survive DB resets). Add codes here to mint new comps.
DEFAULT_COMP_CODES = ("CASH99",)
# Built-in comps are a time-boxed trial: 1 week of premium from the moment of
# redemption, after which the entitlement lapses (auth_middleware treats an
# expired subscription_end_date as unentitled). One redemption per user, so the
# week can't be re-minted by re-entering the code.
DEFAULT_COMP_GRANT_DAYS = 7


async def ensure_default_codes(db: AsyncSession) -> None:
    """Idempotently make sure the built-in free-comp codes exist as free_comp
    rows (premium tier, unlimited). Inserts only what's missing; never updates
    or deletes. Safe to call on every boot."""
    created = []
    for raw in DEFAULT_COMP_CODES:
        code = normalize_code(raw)
        if not code:
            continue
        existing = (
            await db.execute(select(ReferralCode).where(ReferralCode.code == code))
        ).scalar_one_or_none()
        if existing:
            continue
        db.add(ReferralCode(code=code, kind="free_comp", granted_tier="premium", campaign="launch"))
        created.append(code)
    if created:
        await db.commit()
        logger.info("seeded default referral comp codes: %s", ", ".join(created))
