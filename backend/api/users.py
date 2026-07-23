"""
Users API - Profile and Onboarding
"""

import base64
import json
import logging
import math
import re
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Request, Form
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pydantic import BaseModel, Field
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, delete, update

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Timezone-aware UTC now for TIMESTAMPTZ columns (asyncpg-safe)."""
    return datetime.now(timezone.utc)


def _as_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


from db import get_db, get_rds_db, best_effort
from middleware import get_current_user
from services.storage_service import storage_service, delete_by_url
from models.user import (
    UserResponse,
    OnboardingData,
    UserProfile,
    GoalType,
    ExperienceLevel,
    AccountUpdateRequest,
    BlockUserRequest,
    DeleteAccountRequest,
    normalize_intensity_preference,
)
from models.sqlalchemy_models import User, UserProgressPhoto
from models.rds_models import ChannelMessage
from services.sendblue_service import normalize_phone, phone_lookup_candidates
from api.auth import verify_password
from config import settings

router = APIRouter(prefix="/users", tags=["Users"])


class ProgressPhotoBase64Body(BaseModel):
    """Request body for progress photo upload via base64 (avoids multipart issues on RN)."""
    image_base64: str
    face_rating: Optional[float] = None


class SendblueConnectCompleteBody(BaseModel):
    """User preferences when finishing the Sendblue connect screen."""
    sms_opt_in: Optional[bool] = None
    app_notifications_opt_in: Optional[bool] = None


class PushTokenBody(BaseModel):
    """Native APNs device token (hex)."""
    token: str = Field(..., min_length=32, max_length=512)


class NotificationChannelsPatchBody(BaseModel):
    """SMS vs app (APNs) reminder preferences."""
    sms_opt_in: bool
    app_notifications_opt_in: bool


def _normalize_apns_device_token(raw: str) -> str:
    s = re.sub(r"[\s<>]", "", (raw or "").strip()).lower()
    if not re.fullmatch(r"[0-9a-f]+", s):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid device token format")
    if len(s) < 64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Device token too short")
    return s


@router.get("/me/products")
async def get_my_products(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Surface every catalog product relevant to this user's onboarding +
    active maxxes. Used by the Settings → My Products screen.

    Strategy:
      1. Pull the user's onboarding + active schedules.
      2. Derive a set of (module, concerns) pairs from those signals
         (e.g. skinmax + ['acne','dryness'], fitmax + ['muscle_gain']).
      3. Run each pair through find_products() (catalog filter + fact
         filter for vegan / fragrance-allergy / etc).
      4. Dedupe by id, return the union as a list of compact dicts the
         mobile client can render directly.
    Fast (<50ms typical) — pure in-process, no network.
    """
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    ob = dict(user.onboarding or {})
    facts = (
        ob.get("user_facts")
        or (user.persistent_context or {}).get("user_facts") if hasattr(user, "persistent_context") else None
    ) or {}

    # Build (module, concerns) pairs from onboarding signals.
    pairs: list[tuple[str, list[str]]] = []
    if ob.get("primary_skin_concern"):
        pairs.append(("skinmax", [str(ob["primary_skin_concern"])]))
    if ob.get("secondary_skin_concern") and ob["secondary_skin_concern"] != "none":
        pairs.append(("skinmax", [str(ob["secondary_skin_concern"])]))
    if str(ob.get("hair_current_loss") or "").startswith("yes"):
        pairs.append(("hairmax", ["hair_loss", "regrowth"]))
    elif ob.get("hair_current_loss") == "starting":
        pairs.append(("hairmax", ["hair_loss"]))
    if ob.get("fitmax_primary_goal"):
        goal = str(ob["fitmax_primary_goal"])
        concern_map = {
            "muscle": ["muscle_gain", "protein"],
            "lean":   ["recovery", "protein"],
            "both":   ["muscle_gain", "recovery", "protein"],
        }
        pairs.append(("fitmax", concern_map.get(goal, ["protein"])))
    if any(g in (ob.get("goals") or []) for g in ("heightmax", "height")):
        pairs.append(("heightmax", ["posture", "decompression"]))
    if any(g in (ob.get("goals") or []) for g in ("bonemax", "jaw")):
        pairs.append(("bonemax", ["jaw_training", "masseter"]))
    # General fallback so the page isn't empty for new users.
    if not pairs:
        pairs = [("skinmax", []), ("fitmax", [])]

    try:
        from services.product_catalog import find_products
        seen: set[str] = set()
        products: list[dict] = []
        for module, concerns in pairs:
            hits = find_products(
                module=module,
                concerns=concerns or None,
                user_facts=facts,
                limit=4,
            )
            for p in hits:
                if p.id in seen:
                    continue
                seen.add(p.id)
                products.append({
                    "id": p.id,
                    "name": p.name,
                    "brand": p.brand,
                    "module": p.module,
                    "url": p.display_url,
                    "price_tier": p.price_tier,
                    "rationale": p.rationale,
                    "tags": p.tags,
                })
        return {"products": products}
    except Exception as e:
        logger.warning("[my-products] catalog read failed: %s", e)
        return {"products": []}


@router.get("/me", response_model=UserResponse)
async def get_profile(current_user: dict = Depends(get_current_user)):
    """
    Get current user's profile
    """
    ob_raw = dict(current_user.get("onboarding") or {})
    if not ob_raw.get("main_app_tour_completed"):
        cutoff = settings.main_app_tour_cutoff_at
        created = current_user.get("created_at")
        if cutoff and created and _as_utc_aware(created) < _as_utc_aware(cutoff):
            ob_raw["main_app_tour_completed"] = True

    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        first_name=current_user.get("first_name"),
        last_name=current_user.get("last_name"),
        username=current_user.get("username"),
        last_username_change=current_user.get("last_username_change"),
        created_at=current_user["created_at"],
        is_paid=current_user.get("is_paid", False),
        subscription_tier=current_user.get("subscription_tier"),
        subscription_status=current_user.get("subscription_status"),
        subscription_end_date=current_user.get("subscription_end_date"),
        onboarding=OnboardingData(**ob_raw),
        profile=UserProfile(**current_user.get("profile", {})),
        first_scan_completed=current_user.get("first_scan_completed", False),
        is_admin=current_user.get("is_admin", False),
        is_scan_user=current_user.get("is_scan_user", False),
        is_creator=current_user.get("is_creator", False),
        phone_number=current_user.get("phone_number"),
        has_apns_token=current_user.get("has_apns_token", False),
        coaching_tone=current_user.get("coaching_tone") or "default",
    )


@router.post("/push-token")
async def register_push_token(
    body: PushTokenBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Store iOS APNs device token for server-driven push."""
    if not current_user.get("is_paid"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription required")
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    normalized = _normalize_apns_device_token(body.token)
    user.apns_device_token = normalized
    user.apns_token_updated_at = _utcnow()
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok"}


@router.post("/test-push")
async def test_push_notification(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a test push notification to the current user's stored APNs token."""
    from services.apns_service import send_apns_alert, apns_configured, _apns_jwt, apns_response_should_invalidate_token

    if not apns_configured():
        raise HTTPException(status_code=503, detail="Push notifications are not configured on this server")

    try:
        _apns_jwt()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"APNs key is misconfigured: {e}")

    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    token = (user.apns_device_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="No push token registered for this device. Make sure notifications are enabled.")

    ok, http_code = await send_apns_alert(
        token,
        "Max",
        "Push notifications are working! You're all set.",
        badge=1,
    )
    if ok:
        return {"message": "Test notification sent", "apns_status": http_code, "token_prefix": token[:8]}
    if apns_response_should_invalidate_token(http_code):
        user.apns_device_token = None
        user.apns_token_updated_at = None
        await db.commit()
        raise HTTPException(
            status_code=400,
            detail="Your push token was rejected by Apple (expired or invalid). "
                   "Go to Notification preferences, toggle off and back on, then try again.",
        )
    raise HTTPException(status_code=502, detail=f"APNs delivery failed (HTTP {http_code}). Check server logs.")


@router.delete("/push-token")
async def clear_push_token(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove stored APNs token (opt out of push on this device)."""
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.apns_device_token = None
    user.apns_token_updated_at = None
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok"}


@router.patch("/notification-channels")
async def patch_notification_channels(
    body: NotificationChannelsPatchBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update SMS vs app notification preferences (Profile). At least one channel must stay on."""
    if not body.sms_opt_in and not body.app_notifications_opt_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose at least one: SMS or app notifications.",
        )
    if not current_user.get("is_paid"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription required")
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    ob = dict(user.onboarding or {})
    ob["sendblue_sms_opt_in"] = body.sms_opt_in
    ob["app_notifications_opt_in"] = body.app_notifications_opt_in
    user.onboarding = ob
    if not body.app_notifications_opt_in:
        user.apns_device_token = None
        user.apns_token_updated_at = None
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok"}


class CoachingToneBody(BaseModel):
    tone: str = Field(..., description="default | hardcore | gentle | influencer")


class ResponseLengthBody(BaseModel):
    length: str = Field(..., description="concise | medium | detailed")


class IntensityPreferenceBody(BaseModel):
    intensity: str = Field(..., description="chill | standard | sweatmode (synonyms accepted)")


RESPONSE_LENGTH_VALUES = {"concise", "medium", "detailed"}


@router.patch("/response-length")
async def patch_response_length(
    body: ResponseLengthBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set the user's preferred chat response length. Takes effect on the next chat turn."""
    length = (body.length or "").strip().lower()
    if length not in RESPONSE_LENGTH_VALUES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"length must be one of {sorted(RESPONSE_LENGTH_VALUES)}",
        )
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    ob = dict(user.onboarding or {})
    ob["response_length"] = length
    user.onboarding = ob
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok", "length": length}


@router.patch("/coaching-tone")
async def patch_coaching_tone(
    body: CoachingToneBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set the user's preferred coaching tone. Takes effect on the next chat turn."""
    allowed = {"default", "hardcore", "gentle", "influencer"}
    tone = (body.tone or "").strip().lower()
    if tone not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"tone must be one of {sorted(allowed)}",
        )
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.coaching_tone = tone
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok", "tone": tone}


@router.patch("/intensity-preference")
async def patch_intensity_preference(
    body: IntensityPreferenceBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set how aggressively the routine ramps in week 1 (chill | standard | sweatmode).

    Unlike tone/length, this changes the actual schedule shape, so we eagerly
    re-expand the user's live schedules (cheap, <100ms) — week 1 re-ramps
    immediately instead of waiting for the next chat turn.
    """
    intensity = normalize_intensity_preference(body.intensity)
    if intensity is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="intensity must be one of ['chill', 'standard', 'sweatmode']",
        )
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    ob = dict(user.onboarding or {})
    ob["intensity_preference"] = intensity
    user.onboarding = ob
    user.updated_at = datetime.utcnow()
    await db.flush()
    # Persist the preference before the best-effort regen — a regen DB error must
    # not roll back the setting the user just chose (see db.best_effort).
    await db.commit()

    async def _regen():
        from services.schedule_runtime import regenerate_active_schedules
        from services.user_context_service import invalidate as _invalidate_ctx
        _invalidate_ctx(str(user_uuid))
        await regenerate_active_schedules(
            user_id=str(user_uuid), db=db, reason="intensity_preference",
        )
    await best_effort(db, "intensity-preference schedule regen", _regen)
    return {"message": "ok", "intensity": intensity}


@router.post("/post-subscription-onboarding/dismiss")
async def dismiss_post_subscription_onboarding(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clear the flag that triggers post-pay FaceScan results → module select flow."""
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    ob = dict(user.onboarding or {})
    ob["post_subscription_onboarding"] = False
    user.onboarding = ob
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok"}


@router.post("/main-app-tour/complete")
async def complete_main_app_tour(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark the post-pay spotlight tour as completed. Idempotent."""
    if not current_user.get("is_paid"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription required")
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    ob = dict(user.onboarding or {})
    ob["main_app_tour_completed"] = True
    user.onboarding = ob
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok"}


@router.post("/ack-chad-upgrade")
async def ack_chad_upgrade(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clear the one-time "you've been upgraded to Chad" popup flag set by the
    Chad-Lite grandfather migration. Idempotent."""
    user = await db.get(User, UUID(current_user["id"]))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    prof = dict(user.profile or {})
    if prof.pop("chad_upgrade_notice", None) is not None:
        user.profile = prof
        user.updated_at = datetime.utcnow()
        await db.commit()
    return {"message": "ok"}


@router.post("/dev/reset")
async def dev_reset_state(
    body: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DEBUG ONLY: bulk-reset user flags so a single account can replay
    paywall / scan / onboarding without creating a new account.

    Body (all optional, all default False):
      {
        "onboarding": bool,    # clear user.onboarding.completed + reset to {}
        "scan":       bool,    # flip first_scan_completed → false
        "subscription": bool,  # flip is_paid → false, subscription_tier → null
        "all":        bool,    # equivalent to setting all three
      }

    Returns the new state of the affected flags so the client can sync.
    Gated by `settings.debug` — 404s in production. Requires auth so a
    rogue caller can only nuke their own account.
    """
    if not settings.debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    do_all = bool(body.get("all"))
    do_onb = do_all or bool(body.get("onboarding"))
    do_scan = do_all or bool(body.get("scan"))
    do_sub = do_all or bool(body.get("subscription"))

    if do_onb:
        # Wipe onboarding entirely so the user re-runs the questions.
        # Preserve nothing — fresh slate is the dev tool's whole point.
        user.onboarding = {}
        user.questionnaire_v2_completed = None
    if do_scan:
        user.first_scan_completed = False
        user.facial_scan_summary = None
    if do_sub:
        user.is_paid = False
        user.subscription_tier = None

    user.updated_at = datetime.utcnow()
    await db.commit()
    return {
        "message": "ok",
        "reset": {
            "onboarding": do_onb,
            "scan": do_scan,
            "subscription": do_sub,
        },
        "state": {
            "is_paid": bool(user.is_paid),
            "subscription_tier": user.subscription_tier,
            "first_scan_completed": bool(user.first_scan_completed),
            "onboarding_completed": bool((user.onboarding or {}).get("completed")),
        },
    }


@router.post("/dev/mark-scan-completed")
async def dev_mark_scan_completed(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DEBUG ONLY: flip first_scan_completed → true without uploading
    a real scan. Lets devs jump past the scan gate to test downstream
    screens (paywall, module select, home)."""
    if not settings.debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.first_scan_completed = True
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok", "first_scan_completed": True}


@router.post("/sendblue-connect/dev-skip-engage")
async def dev_skip_sendblue_engage_only(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DEBUG ONLY: mark Sendblue engaged without completing the connect step (for notification picker UX)."""
    if not settings.debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    ob = dict(user.onboarding or {})
    ob["sendblue_sms_engaged"] = True
    user.onboarding = ob
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok"}


@router.post("/sendblue-connect/complete")
async def complete_sendblue_connect(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
    prefs: Optional[SendblueConnectCompleteBody] = None,
):
    """Mark post-pay Sendblue intro done. Idempotent: safe to call multiple times."""
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    ob = dict(user.onboarding or {})
    already_completed = ob.get("sendblue_connect_completed") is True
    dev_skip = False
    try:
        if request is not None:
            dev_skip = str(request.headers.get("x-dev-skip-sendblue", "")).strip() == "1"
    except Exception:
        dev_skip = False
    user_is_skipping_sms = prefs is not None and prefs.sms_opt_in is False
    if (
        ob.get("sendblue_sms_engaged") is not True
        and not already_completed
        and not (settings.debug and dev_skip)
        and not user_is_skipping_sms
    ):
        raise HTTPException(
            status_code=400,
            detail="We have not received a message from your number yet. Text the Max line from the phone on your account, wait a few seconds, then try again.",
        )
    # Dev-only escape hatch so local/dev builds can proceed without texting.
    if settings.debug and dev_skip:
        ob["sendblue_sms_engaged"] = True

    # Store user opt-in/out preferences (defaults stay whatever was already on file).
    if prefs is not None:
        if prefs.sms_opt_in is not None:
            ob["sendblue_sms_opt_in"] = prefs.sms_opt_in
        if prefs.app_notifications_opt_in is not None:
            ob["app_notifications_opt_in"] = prefs.app_notifications_opt_in

    ob["sendblue_connect_completed"] = True
    user.onboarding = ob
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok"}


@router.post("/onboarding")
async def save_onboarding(
    data: OnboardingData,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Save onboarding questionnaire answers
    """
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update onboarding data (normalize body metrics to chosen unit system)
    onboarding_data = data.model_dump()
    # Strip server-owned entitlement keys — marketplace access is derived from
    # the Purchase table, never from a client-supplied onboarding field (P0-1).
    for _entitlement_key in ("entered_maxxes", "entered_courses"):
        onboarding_data.pop(_entitlement_key, None)
    # This endpoint REPLACES user.onboarding wholesale, so a partial payload from
    # a future screen would wipe server-authored keys (lock-ins, notif prefs, tour
    # flags, post-pay steps). Preserve those from the existing blob and never take
    # them from the request body. (Client-settable keys like intensity_preference
    # and chat-owned response_length are intentionally NOT in this set.)
    _SERVER_OWNED = (
        "maxx_entered_at", "lock_ins", "confirmed_facts", "notif_category_prefs",
        "sendblue_sms_opt_in", "app_notifications_opt_in", "main_app_tour_completed",
        "post_subscription_onboarding", "sendblue_connect_completed",
        "notification_channels_completed", "module_select_completed",
    )
    _existing_ob = dict(user.onboarding or {})
    for _k in _SERVER_OWNED:
        if _k in _existing_ob:
            onboarding_data[_k] = _existing_ob[_k]
        else:
            onboarding_data.pop(_k, None)
    unit = str(onboarding_data.get("unit_system") or "imperial").strip().lower()
    height = onboarding_data.get("height")
    weight = onboarding_data.get("weight")

    def _round1(x):
        try:
            return round(float(x), 1)
        except Exception:
            return None

    height_f = _round1(height) if height is not None else None
    weight_f = _round1(weight) if weight is not None else None

    # Canonical always-metric values
    height_cm = None
    weight_kg = None

    if unit == "metric":
        # height: cm, weight: kg
        height_cm = height_f
        weight_kg = weight_f
        onboarding_data["height"] = height_cm
        onboarding_data["weight"] = weight_kg
    else:
        # imperial: height: inches, weight: lbs
        # Back-compat heuristics: older clients may still send cm/kg even when unit_system=imperial.
        # - Height: if > 120, it's almost certainly cm; convert to inches.
        # - Weight: if < 120, it's likely kg for most adults; convert to lbs.
        inches = height_f
        lbs = weight_f
        if inches is not None and inches > 120:
            inches = _round1(inches / 2.54)
        if lbs is not None and lbs < 120:
            lbs = _round1(lbs * 2.20462)

        onboarding_data["height"] = inches
        onboarding_data["weight"] = lbs
        height_cm = _round1(inches * 2.54) if inches is not None else None
        weight_kg = _round1(lbs * 0.453592) if lbs is not None else None

    onboarding_data["height_cm"] = height_cm
    onboarding_data["weight_kg"] = weight_kg
    # Legacy clients never send `completed` and rely on the save marking the
    # funnel done. Onboarding v2 saves mid-funnel with an EXPLICIT
    # completed=false (the reveal + permission steps still follow) - honor it,
    # otherwise the root navigator swaps stacks mid-flow and the reveal is
    # silently skipped for every new user.
    if "completed" not in data.model_fields_set:
        onboarding_data["completed"] = True

    # Fits-your-life resolution: the human answers ("workout after work",
    # "I sleep in on weekends") become concrete windows derived from the
    # user's OWN anchors, so every placement pass downstream honors them.
    choice = str(onboarding_data.get("workout_window_choice") or "").strip()
    if choice:
        from services.human_time import hm as _ht_hm, resolve_workout_window
        lo, hi = resolve_workout_window(onboarding_data, choice)
        onboarding_data["preferred_workout_window"] = [
            _ht_hm(lo % (24 * 60)), _ht_hm(hi % (24 * 60)),
        ]

    # Commute becomes real, visible, protected time. If the user gave a
    # commute and isn't fully remote, bracket their main work block with
    # "Commute" obligations so the scheduler never lands a task while they're
    # in transit — and so the block shows up on their week. Derived blocks are
    # tagged so re-saving (edit-lifestyle) replaces rather than duplicates them.
    from services.human_time import hm as _ht_hm_c, to_min as _ht_to_min_c
    try:
        commute_min = int(onboarding_data.get("commute_minutes") or 0)
    except (TypeError, ValueError):
        commute_min = 0
    work_location = str(onboarding_data.get("work_location") or "").strip().lower()
    obs = [
        o for o in (onboarding_data.get("obligations") or [])
        if not (isinstance(o, dict) and o.get("_derived") == "commute")
    ]
    if commute_min > 0 and work_location != "home":
        work_ob = None
        for o in obs:
            if not isinstance(o, dict):
                continue
            s, e = _ht_to_min_c(o.get("start"), -1), _ht_to_min_c(o.get("end"), -1)
            if 0 <= s < e and (e - s) >= 3 * 60:
                cur = (e - s)
                best = (
                    _ht_to_min_c(work_ob.get("end"), 0) - _ht_to_min_c(work_ob.get("start"), 0)
                    if work_ob else -1
                )
                if cur > best:
                    work_ob = o
        if work_ob is not None:
            ws = _ht_to_min_c(work_ob.get("start"), -1)
            we = _ht_to_min_c(work_ob.get("end"), -1)
            days = work_ob.get("days") or "weekdays"
            if 0 <= ws - commute_min:
                obs.append({
                    "label": "Commute", "start": _ht_hm_c(ws - commute_min),
                    "end": _ht_hm_c(ws), "days": days, "_derived": "commute",
                })
            if we + commute_min <= 24 * 60 - 5:
                obs.append({
                    "label": "Commute home", "start": _ht_hm_c(we),
                    "end": _ht_hm_c(we + commute_min), "days": days, "_derived": "commute",
                })
    onboarding_data["obligations"] = obs

    if onboarding_data.get("weekend_shift") and not (
        onboarding_data.get("weekly_timings") or {}
    ).get("saturday"):
        from services.human_time import hm as _ht_hm2, to_min as _ht_to_min
        wake_m = _ht_to_min(onboarding_data.get("wake_time"), 7 * 60)
        sleep_m = _ht_to_min(onboarding_data.get("sleep_time"), 23 * 60)
        weekend = {
            "wake_time": _ht_hm2((wake_m + 60) % (24 * 60)),
            "sleep_time": _ht_hm2((sleep_m + 60) % (24 * 60)),
        }
        wt = dict(onboarding_data.get("weekly_timings") or {})
        wt["saturday"] = {**weekend, **(wt.get("saturday") or {})}
        wt["sunday"] = {**weekend, **(wt.get("sunday") or {})}
        onboarding_data["weekly_timings"] = wt
    user.onboarding = onboarding_data
    user.updated_at = datetime.utcnow()
    await db.flush()
    # Commit the ONE thing that must persist — onboarding `completed` — BEFORE any
    # best-effort side-effect. A DB error in a side-effect aborts the shared
    # transaction, which would turn the final commit into a silent ROLLBACK and
    # strand the user mid-funnel (completed never sticks, the client keeps reading
    # completed:false and never advances). See db.best_effort.
    await db.commit()

    # Mirror durable profile facts (wake/sleep, skin/hair type, equipment, ...)
    # into user_facts so they're part of KNOWN PROFILE and never re-asked when
    # the user later sets up a different maxx. THE bug this fixes: onboarding
    # answers used to live only in user.onboarding, so per-maxx intake (which
    # reads user_facts) couldn't see them and re-asked. Isolated: a failure here
    # can't undo the onboarding save above.
    async def _sync_user_facts():
        from services.user_facts_service import facts_from_onboarding, merge_facts, FACTS_KEY
        from services.user_context_service import get_context, merge_context
        ob_facts = facts_from_onboarding(onboarding_data)
        if ob_facts:
            existing_ctx = await get_context(str(user_uuid), db)
            merged = merge_facts(existing_ctx.get(FACTS_KEY) or {}, ob_facts)
            await merge_context(str(user_uuid), {FACTS_KEY: merged}, db)
    await best_effort(db, "onboarding->user_facts sync", _sync_user_facts)

    # Editing lifestyle (wake/sleep/work hours, workout time, get-ready time)
    # must propagate to the user's live schedules immediately — otherwise the
    # precise timings the user just set wouldn't take effect until they touch
    # the chatbot. Skeleton re-expansion is pure-Python (<100ms) and only
    # writes when something actually changed, so this is cheap to do eagerly.
    async def _regen_schedules():
        from services.schedule_runtime import regenerate_active_schedules
        from services.user_context_service import invalidate as _invalidate_ctx
        _invalidate_ctx(str(user_uuid))
        await regenerate_active_schedules(
            user_id=str(user_uuid), db=db, reason="edit_lifestyle",
        )
    await best_effort(db, "post-onboarding schedule regen", _regen_schedules)

    # Fold the fresh onboarding answers into the unified personalization profile
    # so the chat brief + scheduler signals reflect them immediately.
    async def _rebuild_personalization():
        from services.personalization import rebuild_profile as _rebuild_pers
        await _rebuild_pers(str(user_uuid), db)
    await best_effort(db, "post-onboarding personalization rebuild", _rebuild_personalization)

    # Product decision: onboarding no longer PRESETS any max. A brand-new user
    # lands with an empty plan and chooses the maxes they want in the marketplace
    # (Explore), onboarding each one themselves via its chat flow. So we don't
    # auto-build a #1-priority routine here anymore — the reveal is just a taste.
    first_routine = None

    # `first_routine` (when present) lets the client reveal the freshly-built
    # plan right after onboarding, BEFORE the paywall — the schedule endpoints
    # are paid-gated, so we hand the preview back inline here instead.
    return {
        "message": "Onboarding completed",
        "data": onboarding_data,
        "first_routine": _starter_preview(first_routine),
    }


def _starter_preview(routine: Optional[dict]) -> Optional[dict]:
    """Trim a generated routine to a lightweight reveal payload: the maxx, a
    title, and the first populated day's tasks (time + title only). Keeps the
    onboarding response small and free of internal scheduling fields."""
    if not routine:
        return None
    days = routine.get("days") or []
    first_day = next((d for d in days if (d.get("tasks") or [])), None)
    tasks = []
    for t in (first_day or {}).get("tasks", []) if first_day else []:
        tasks.append({
            "time": t.get("time"),
            "title": t.get("title") or t.get("catalog_id") or "Task",
        })
    return {
        "maxx_id": routine.get("maxx_id"),
        "course_title": routine.get("course_title"),
        "starter": bool(routine.get("starter")),
        "day_count": len(days),
        "sample_day": tasks,
    }


@router.post("/onboarding/anonymous")
async def save_onboarding_anonymous(data: OnboardingData):
    """
    Public onboarding endpoint used before login/signup.

    This does NOT persist anything by itself. It simply validates and
    echoes back the onboarding payload so the client can carry it through
    signup and attach it to the real user account afterwards.
    """
    # Ensure completed flag is set on the payload the same way as the authed endpoint
    onboarding_data = data.model_dump()
    onboarding_data["completed"] = True
    return {"message": "Onboarding captured", "data": onboarding_data}


# --------------------------------------------------------------------------- #
#  Planner chatbot — natural-language edits to the weekly daily-rhythm plan   #
# --------------------------------------------------------------------------- #

_WEEKDAY_KEYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_DEFAULT_TIME_FIELDS = (
    "wake_time", "sleep_time", "get_ready_time",
    "preferred_workout_time", "work_start", "work_end",
)

# Obligation `days` recurrence — canonical tokens + the weekday-name vocabulary.
_WEEKDAYS_MF = frozenset(_WEEKDAY_KEYS[:5])
_WEEKENDS_SS = frozenset(_WEEKDAY_KEYS[5:])
_WEEKDAY_SET = frozenset(_WEEKDAY_KEYS)
_DAY_ALIASES = {
    "mon": "monday", "monday": "monday",
    "tue": "tuesday", "tues": "tuesday", "tuesday": "tuesday",
    "wed": "wednesday", "weds": "wednesday", "wednesday": "wednesday",
    "thu": "thursday", "thur": "thursday", "thurs": "thursday", "thursday": "thursday",
    "fri": "friday", "friday": "friday",
    "sat": "saturday", "saturday": "saturday",
    "sun": "sunday", "sunday": "sunday",
}


def _norm_hhmm(v) -> Optional[str]:
    """Coerce a value to canonical 'HH:MM' 24h, or None if not a valid clock."""
    if not isinstance(v, str):
        return None
    m = _HHMM_RE.match(v.strip())
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _add_minutes(hhmm: str, delta: int) -> str:
    """Shift an 'HH:MM' clock by `delta` minutes, wrapping within a day."""
    total = (int(hhmm[:2]) * 60 + int(hhmm[3:5]) + delta) % 1440
    return f"{total // 60:02d}:{total % 60:02d}"


def _window_mid(win: List[str]) -> str:
    """Midpoint 'HH:MM' of a [start, end] window (both canonical HH:MM)."""
    a = int(win[0][:2]) * 60 + int(win[0][3:5])
    b = int(win[1][:2]) * 60 + int(win[1][3:5])
    mid = (a + b) // 2
    return f"{mid // 60:02d}:{mid % 60:02d}"


def _norm_window(v) -> Optional[List[str]]:
    """Normalize a [start, end] HH:MM window. None if invalid or non-positive."""
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        return None
    a = _norm_hhmm(v[0])
    b = _norm_hhmm(v[1])
    if not a or not b or b <= a:
        return None
    return [a, b]


def _norm_days(v) -> object:
    """Normalize an obligation's `days` recurrence to a canonical form:
    "all" | "weekdays" | "weekends" | sorted list of weekday names.

    Accepts fuzzy tokens ("everyday", "wknd"), day abbreviations ("mon"), and
    lists mixing names + tokens. A full Mon-Fri / Sat-Sun / 7-day set collapses
    back to its token. Anything unrecognized falls back to "all" so a
    commitment is never silently dropped from every day.
    """
    if isinstance(v, str):
        t = v.strip().lower()
        if t in ("", "all", "everyday", "every day", "daily", "any", "every"):
            return "all"
        if t in ("weekday", "weekdays", "wkday", "wkdays"):
            return "weekdays"
        if t in ("weekend", "weekends", "wknd", "wknds"):
            return "weekends"
        d = _DAY_ALIASES.get(t)
        return [d] if d else "all"
    if isinstance(v, (list, tuple)):
        acc: set = set()
        for it in v:
            if not isinstance(it, str):
                continue
            t = it.strip().lower()
            if t in ("weekday", "weekdays"):
                acc |= _WEEKDAYS_MF
            elif t in ("weekend", "weekends"):
                acc |= _WEEKENDS_SS
            elif t in ("all", "everyday", "daily"):
                acc |= _WEEKDAY_SET
            else:
                d = _DAY_ALIASES.get(t)
                if d:
                    acc.add(d)
        if not acc or acc == _WEEKDAY_SET:
            return "all"
        if acc == _WEEKDAYS_MF:
            return "weekdays"
        if acc == _WEEKENDS_SS:
            return "weekends"
        return sorted(acc, key=_WEEKDAY_KEYS.index)
    return "all"


def _norm_obligations(raw) -> Optional[List[dict]]:
    """Normalize an obligations list — drop malformed / zero-length entries,
    preserving each item's `days` recurrence (default "all")."""
    if not isinstance(raw, list):
        return None
    out: List[dict] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        s = _norm_hhmm(it.get("start"))
        e = _norm_hhmm(it.get("end"))
        if not s or not e or e <= s:
            continue
        lbl = (str(it.get("label") or "busy").strip() or "busy")[:40]
        out.append({"label": lbl, "start": s, "end": e, "days": _norm_days(it.get("days"))})
    return out


def _norm_day_fields(raw) -> dict:
    """Normalize one weekday-override dict to only valid, known fields."""
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for k in _DEFAULT_TIME_FIELDS:
        v = _norm_hhmm(raw.get(k))
        if v:
            out[k] = v
    ws = raw.get("work_schedule")
    if isinstance(ws, str) and ws.strip().lower() in ("fixed", "flexible"):
        out["work_schedule"] = ws.strip().lower()
    if "obligations" in raw:
        obs = _norm_obligations(raw.get("obligations"))
        if obs is not None:
            out["obligations"] = obs
    return out


def _loads_lenient(raw: str) -> dict:
    """Parse an LLM JSON reply tolerantly.

    Providers run in JSON mode so the reply is usually a clean object, but some
    still wrap it in ```json fences``` or add stray prose. Strip a fence if
    present, then fall back to scanning for the first balanced {...} block.
    Returns {} when nothing usable parses (caller treats that as a soft error).
    """
    if not isinstance(raw, str):
        return {}
    s = raw.strip()
    if not s:
        return {}
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9]*\s*", "", s)
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    try:
        out = json.loads(s)
        return out if isinstance(out, dict) else {}
    except Exception:
        pass
    # Fall back: extract the first balanced object (handles leading/trailing prose).
    start = s.find("{")
    if start == -1:
        return {}
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    out = json.loads(s[start:i + 1])
                    return out if isinstance(out, dict) else {}
                except Exception:
                    return {}
    return {}


def _clean_summary_voice(text: str) -> str:
    """Blunt-voice guard for the user-facing planner summary.

    The summary is the one line we surface from the LLM after a plan edit.
    House style: no em-dashes, no markdown emphasis. The model's few-shot
    examples already follow this, but we enforce it deterministically so a
    stray em-dash or **bold** never reaches the user. Hyphenated ranges like
    "6-7 PM" are preserved; a numeric em-dash range collapses to a hyphen,
    and an em-dash used as a clause break becomes a comma (it's a single
    sentence, so that's what it always is).
    """
    if not isinstance(text, str) or not text:
        return text
    t = re.sub(r"(?<=\d)\s*—\s*(?=\d)", "-", text)        # 6—7 -> 6-7 (range)
    t = t.replace("—", ", ").replace("―", ", ")      # em-dash / bar -> comma
    t = t.replace("–", "-")                               # en-dash -> hyphen (ranges)
    t = t.replace("**", "").replace("*", "").replace("`", "")  # strip markdown emphasis/code
    t = re.sub(r"\s+([,.!?])", r"\1", t)                       # tidy space-before-punctuation
    t = re.sub(r",\s*([.!?])", r"\1", t)                       # ", ." -> "."
    t = re.sub(r"\s{2,}", " ", t)                              # collapse runs of spaces
    t = re.sub(r"\s*,\s*$", "", t)                             # no trailing comma
    return t.strip()


def _build_planner_prompt(cur_defaults: dict, cur_weekly: dict, instruction: str) -> str:
    """Build the planner-chat LLM prompt. Pure (no I/O) so it can be tested /
    exercised against the live model without going through the HTTP endpoint."""
    return (
        "You translate a natural-language request into a STRUCTURED EDIT of a user's\n"
        "WEEKLY daily-rhythm plan for a self-improvement app whose goal is to fit\n"
        "healthy routines into a real life — never to force an unrealistic day.\n\n"
        "DATA MODEL\n"
        "- DEFAULTS apply to all 7 days.\n"
        "- PER-WEEKDAY OVERRIDES replace specific fields on specific days (a weekend\n"
        "  lie-in, a later Monday wake). An override only changes the fields it lists;\n"
        "  any field it omits falls back to the default for that day.\n"
        "- Editing is PRESENCE-BASED: only the fields/days you return are touched.\n"
        "  Everything you omit is kept exactly as it is now.\n\n"
        "FIELDS\n"
        "- wake_time, sleep_time, get_ready_time — scalar \"HH:MM\" (24-hour).\n"
        "- preferred_workout_window — a [\"HH:MM\",\"HH:MM\"] START/END time RANGE reserved\n"
        "  for working out (NOT a single instant). \"gym at 6pm\" becomes a ~1-hour window\n"
        "  e.g. [\"18:00\",\"19:00\"]; \"workout 5-7pm\" -> [\"17:00\",\"19:00\"].\n"
        "- obligations — a LIST of fixed commitments to plan AROUND, each\n"
        "  {\"label\", \"start\" \"HH:MM\", \"end\" \"HH:MM\", \"days\"}. WORK or SCHOOL is just an\n"
        "  obligation (e.g. {\"label\":\"Work\",\"start\":\"09:00\",\"end\":\"17:00\",\"days\":\"weekdays\"}).\n"
        "  `days` is the recurrence — how often that commitment repeats:\n"
        "    \"all\" (every day), \"weekdays\" (Mon-Fri), \"weekends\" (Sat+Sun),\n"
        "    or a list of specific lowercase day names, e.g. [\"monday\",\"wednesday\",\"friday\"].\n\n"
        f"CURRENT DEFAULTS:\n{json.dumps(cur_defaults, ensure_ascii=False)}\n\n"
        f"CURRENT PER-WEEKDAY OVERRIDES:\n{json.dumps(cur_weekly, ensure_ascii=False)}\n\n"
        f"USER REQUEST: \"{instruction}\"\n\n"
        "HOW TO INTERPRET\n"
        "- Resolve RELATIVE / FUZZY phrasing against the CURRENT values above. \"sleep in\n"
        "  an hour on weekends\" = current wake_time + 60 min on sat+sun. \"wake a bit\n"
        "  earlier\" with no amount ~= 30 min earlier. \"workout in the evening\" ~=\n"
        "  [\"18:00\",\"19:00\"], \"morning\" ~= [\"07:00\",\"08:00\"], \"at lunch\" ~= [\"12:00\",\"13:00\"].\n"
        "- WHICH DAYS does a commitment repeat on? \"gym Mon Wed Fri\" -> days\n"
        "  [\"monday\",\"wednesday\",\"friday\"]; \"work 9-5\" (no day said) -> \"weekdays\";\n"
        "  an everyday routine -> \"all\"; \"on weekends\" -> \"weekends\".\n"
        "- MINIMAL DIFF: return ONLY the fields that actually change. Inside a weekday\n"
        "  override, include ONLY the fields that DIFFER from the default — never echo\n"
        "  unchanged fields.\n"
        "- DEFAULTS vs PER-DAY: a wake / sleep / get-ready / workout change that applies\n"
        "  to ALL 7 days goes in \"defaults\"; one for only SOME days goes in weekly_timings,\n"
        "  one entry per named day (NEVER enumerate all seven). Obligations are NOT\n"
        "  per-day overrides — express their recurrence with each obligation's own `days`\n"
        "  field and keep the list in defaults.obligations.\n"
        "- obligations is REPLACED wholesale, not merged. To ADD or REMOVE one, return the\n"
        "  COMPLETE new list (re-listing the existing ones you keep), each with its `days`.\n"
        "  To remove every obligation, return [].\n"
        "- To CLEAR a scalar field, set it to null; to remove the workout, set\n"
        "  preferred_workout_window to null. To CLEAR a whole day's overrides, set that\n"
        "  day to {}.\n"
        "- Apply ALL changes in a multi-part request together.\n"
        "- Respect what the user asks even if it seems early/late; it's their day. But do\n"
        "  NOT invent commitments, labels, or times they didn't state. Labels <= 3 words.\n"
        "- Make NO changes (return empty defaults and weekly_timings) and explain in the\n"
        "  summary if the request is ambiguous, isn't about daily timings, or names a\n"
        "  specific calendar date instead of a weekday — ask for the missing detail.\n\n"
        "OUTPUT — STRICT JSON ONLY. No markdown, no code fences, no prose outside the JSON:\n"
        "{\n"
        "  \"defaults\": { ...only default-level fields you are CHANGING... },\n"
        "  \"weekly_timings\": { \"saturday\": { ...fields... }, ... only the days you are CHANGING ... },\n"
        "  \"summary\": \"<one short, plain sentence naming exactly what changed and on which days. Blunt and friendly. No em-dashes, no markdown, no asterisks.>\"\n"
        "}\n\n"
        "EXAMPLES (shape only — real current values vary per user):\n"
        "- \"I sleep in until 10 on weekends\" ->\n"
        "  {\"weekly_timings\":{\"saturday\":{\"wake_time\":\"10:00\"},\"sunday\":{\"wake_time\":\"10:00\"}},\"summary\":\"You'll now wake at 10:00 on Saturday and Sunday.\"}\n"
        "- \"move my workout to the evening\" ->\n"
        "  {\"defaults\":{\"preferred_workout_window\":[\"18:00\",\"19:00\"]},\"summary\":\"Moved your workout window to 6-7 PM.\"}\n"
        "- \"I go to the gym 6-7pm on Mon, Wed and Fri\" (current obligations: Work 09:00-17:00 weekdays) ->\n"
        "  {\"defaults\":{\"obligations\":[{\"label\":\"Work\",\"start\":\"09:00\",\"end\":\"17:00\",\"days\":\"weekdays\"},{\"label\":\"Gym\",\"start\":\"18:00\",\"end\":\"19:00\",\"days\":[\"monday\",\"wednesday\",\"friday\"]}]},\"summary\":\"Added the gym 6-7 PM on Mon, Wed and Fri.\"}\n"
        "- \"I work 9 to 5 on weekdays\" (no current obligations) ->\n"
        "  {\"defaults\":{\"obligations\":[{\"label\":\"Work\",\"start\":\"09:00\",\"end\":\"17:00\",\"days\":\"weekdays\"}]},\"summary\":\"Set work 9-5 on weekdays.\"}\n"
        "- \"remove my workout\" ->\n"
        "  {\"defaults\":{\"preferred_workout_window\":null},\"summary\":\"Removed your workout window.\"}\n"
        "- \"clear my Wednesday changes\" ->\n"
        "  {\"weekly_timings\":{\"wednesday\":{}},\"summary\":\"Cleared your Wednesday overrides.\"}\n"
    )


def _apply_planner_diff(prev: dict, cur_weekly: dict, parsed: dict) -> bool:
    """Merge a parsed planner diff into `prev` (mutated in place).

    Presence-based: only the default fields and weekday keys present in
    `parsed` are touched; everything omitted is kept. `obligations` (default
    or per-day) is REPLACED wholesale with the normalized list. Returns True
    if anything changed. Pure + DB-free so it can be unit-tested directly.
    """
    changed = False
    d = parsed.get("defaults") if isinstance(parsed.get("defaults"), dict) else {}
    for key in _DEFAULT_TIME_FIELDS:
        if key not in d:
            continue
        raw_v = d.get(key)
        if raw_v is None:
            # Explicit null = clear the field.
            if prev.get(key) is not None:
                changed = True
            prev[key] = None
        else:
            norm = _norm_hhmm(raw_v)
            if norm is not None:
                prev[key] = norm
                changed = True
            # else: model emitted an unparseable time — ignore it rather than
            # silently wiping the user's existing value.
    if "preferred_workout_window" in d:
        raw_w = d.get("preferred_workout_window")
        if raw_w is None:
            # Explicit null = remove the workout window (and its synced scalar).
            if prev.get("preferred_workout_window") is not None or prev.get("preferred_workout_time") is not None:
                changed = True
            prev["preferred_workout_window"] = None
            prev["preferred_workout_time"] = None
        else:
            nw = _norm_window(raw_w)
            if nw is not None:
                prev["preferred_workout_window"] = nw
                prev["preferred_workout_time"] = _window_mid(nw)  # keep scalar in sync (back-compat)
                changed = True
            # else: malformed window — ignore rather than wipe the existing one.
    if "work_schedule" in d:
        ws = d.get("work_schedule")
        prev["work_schedule"] = (
            ws.strip().lower()
            if isinstance(ws, str) and ws.strip().lower() in ("fixed", "flexible")
            else None
        )
        changed = True
    if "obligations" in d:
        prev["obligations"] = _norm_obligations(d.get("obligations")) or None
        changed = True

    wk_in = parsed.get("weekly_timings") if isinstance(parsed.get("weekly_timings"), dict) else {}
    wk_out = dict(cur_weekly or {})
    for day in _WEEKDAY_KEYS:
        if day not in wk_in:
            continue
        cleaned = _norm_day_fields(wk_in.get(day))
        if cleaned:
            wk_out[day] = cleaned
        else:
            wk_out.pop(day, None)  # explicit {} → clear this day's override
        changed = True
    prev["weekly_timings"] = wk_out or None
    return changed


def _migrate_work_to_obligation(prev: dict) -> bool:
    """Fold a legacy fixed work block (work_schedule/work_start/work_end) into the
    obligations list as a weekday "Work" item, then drop the legacy work_* fields.
    Idempotent; mutates `prev`; returns True if anything changed.

    Keeps the planner-chat view consistent with the new "work is just an
    obligation" model, so an edit can't leave a user with BOTH a work block and a
    Work obligation (which the scheduler would double-book).
    """
    touched = False
    ws = prev.get("work_schedule")
    ws = ws.strip().lower() if isinstance(ws, str) else ""
    start = _norm_hhmm(prev.get("work_start"))
    end = _norm_hhmm(prev.get("work_end"))
    if ws == "fixed" and start and end:
        obs = prev.get("obligations")
        obs = list(obs) if isinstance(obs, list) else []
        has_work = any(
            isinstance(o, dict) and str(o.get("label", "")).strip().lower() in ("work", "school")
            for o in obs
        )
        if not has_work:
            obs.append({"label": "Work", "start": start, "end": end, "days": "weekdays"})
            prev["obligations"] = _norm_obligations(obs) or obs
            touched = True
    # Drop the legacy work scaffolding (migrated above, or flexible/none → irrelevant now).
    for k in ("work_schedule", "work_start", "work_end"):
        if prev.get(k) is not None:
            prev[k] = None
            touched = True
    return touched


def _public_defaults(state: dict) -> dict:
    """The default-level plan we surface to the planner client + LLM, in the new
    workout-window + obligations(-with-`days`) model. A legacy single workout
    time is presented as a 90-minute window for a consistent shape."""
    out: dict = {}
    for k in ("wake_time", "sleep_time", "get_ready_time"):
        v = _norm_hhmm(state.get(k))
        if v:
            out[k] = v
    win = _norm_window(state.get("preferred_workout_window"))
    if not win:
        wt = _norm_hhmm(state.get("preferred_workout_time"))
        if wt:
            win = [wt, _add_minutes(wt, 90)]
    if win:
        out["preferred_workout_window"] = win
    obs = state.get("obligations")
    if isinstance(obs, list) and obs:
        out["obligations"] = obs
    return out


class PlannerChatBody(BaseModel):
    instruction: str = Field(..., description="Natural-language change request for the weekly plan.")


@router.post("/planner/chat")
async def planner_chat(
    body: PlannerChatBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply a natural-language edit to the user's weekly daily-rhythm plan.

    The user types something like "I sleep in until 10 on weekends" or
    "add gym 6-7pm on Mon, Wed, Fri" and an LLM translates it into a
    structured diff over the default timings + per-weekday overrides. We
    merge the diff into onboarding (presence-based, so unmentioned fields are
    never touched), persist via the same path as save_onboarding (regenerate
    live schedules + invalidate coach context), and return the new state.
    """
    import asyncio

    instruction = (body.instruction or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction is required")

    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    prev = dict(user.onboarding or {})
    _migrate_work_to_obligation(prev)  # legacy fixed-work block → weekday "Work" obligation
    cur_defaults = _public_defaults(prev)
    cur_weekly = prev.get("weekly_timings") if isinstance(prev.get("weekly_timings"), dict) else {}

    prompt = _build_planner_prompt(cur_defaults, cur_weekly, instruction)

    try:
        from services.llm_sync import async_llm_json_response
        raw = await asyncio.wait_for(async_llm_json_response(prompt, max_tokens=1200), timeout=30)
    except Exception as e:
        logger.warning("planner_chat LLM call failed: %s", e)
        raise HTTPException(status_code=502, detail="Couldn't reach the planner just now. Try again in a moment.")

    parsed = _loads_lenient(raw)
    if not parsed:
        logger.warning("planner_chat: unparseable LLM reply (%d chars)", len(raw or ""))
        raise HTTPException(status_code=502, detail="Couldn't understand that. Try rephrasing it.")

    summary = _clean_summary_voice(str(parsed.get("summary") or "").strip())[:240] or "Updated your plan."

    # --- Merge the diff into onboarding (presence-based: unmentioned = keep) --
    changed = _apply_planner_diff(prev, cur_weekly, parsed)

    if not changed:
        # Nothing actionable — return current state untouched, with the
        # model's explanation (e.g. "I couldn't tell which day you meant").
        return {
            "message": "No changes applied",
            "summary": summary,
            "defaults": cur_defaults,
            "weekly_timings": cur_weekly or None,
            "changed": False,
        }

    prev["completed"] = True
    user.onboarding = prev
    user.updated_at = datetime.utcnow()
    await db.flush()
    # Persist the plan update before the best-effort regen so a regen DB error
    # can't roll it back (see db.best_effort).
    await db.commit()

    # Propagate to live schedules + coach context, same as save_onboarding.
    async def _regen():
        from services.schedule_runtime import regenerate_active_schedules
        from services.user_context_service import invalidate as _invalidate_ctx
        _invalidate_ctx(str(user_uuid))
        await regenerate_active_schedules(user_id=str(user_uuid), db=db, reason="planner_chat")
    await best_effort(db, "planner_chat schedule regen", _regen)

    return {
        "message": "Plan updated",
        "summary": summary,
        "defaults": _public_defaults(prev),
        "weekly_timings": prev.get("weekly_timings"),
        "changed": True,
    }


_MAX_IMAGE_BYTES = 12 * 1024 * 1024  # 12 MB — mirror /scans/upload's cap


def _validate_image_upload(data: bytes, content_type: Optional[str], label: str) -> None:
    """Reject oversized or non-image uploads before they hit memory/storage.

    Without this, upload_avatar / upload_progress_photo `await file.read()` the
    entire body into memory with no bound — a memory-exhaustion vector.
    """
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"{label} image is too large (max {_MAX_IMAGE_BYTES // (1024 * 1024)}MB).",
        )
    ct = (content_type or "").lower()
    if ct and not ct.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"{label} must be an image.")


@router.post("/me/review-opened")
async def mark_review_opened(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record that the native App Store review prompt was requested for this user.
    Apple never tells us whether the user actually rated, so we count REQUESTS to
    enforce the cross-install throttle (Apple itself only shows the sheet ~3x/yr).
    The client also keeps a local same-session throttle. Best-effort + idempotent-ish."""
    from sqlalchemy.orm.attributes import flag_modified
    user = await db.get(User, UUID(current_user["id"]))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    profile = dict(user.profile or {})
    profile["review_request_count"] = int(profile.get("review_request_count") or 0) + 1
    profile["last_review_request_date"] = datetime.now(timezone.utc).date().isoformat()
    user.profile = profile
    flag_modified(user, "profile")
    await db.commit()
    return {
        "review_request_count": profile["review_request_count"],
        "last_review_request_date": profile["last_review_request_date"],
    }


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload profile picture
    """
    # Bounded read: cap+1 so an oversized body 413s in _validate_image_upload
    # without first being buffered whole into RAM.
    content = await file.read(_MAX_IMAGE_BYTES + 1)
    _validate_image_upload(content, file.content_type, "Avatar")

    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        if user.profile and user.profile.get("avatar_url"):
            delete_by_url(user.profile.get("avatar_url"))
    except Exception as e:
        logger.warning("Avatar cleanup failed: %s", e)

    avatar_url = await storage_service.upload_image(
        content,
        current_user["id"],
        image_type="avatar"
    )

    if not avatar_url:
        raise HTTPException(status_code=500, detail="Failed to upload image")

    # Assign a new dict to ensure SQLAlchemy tracks JSON changes
    current_profile = dict(user.profile or {})
    current_profile["avatar_url"] = avatar_url
    user.profile = current_profile
    user.updated_at = datetime.utcnow()
    await db.commit()
    
    return {"avatar_url": avatar_url}


@router.put("/profile")
async def update_profile(
    profile: UserProfile,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update user profile
    """
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Merge with existing profile data to avoid overwriting unrelated fields
    current_profile = dict(user.profile or {})
    updated_data = profile.model_dump(exclude_unset=True)
    
    for key, value in updated_data.items():
        current_profile[key] = value

    user.profile = current_profile
    user.updated_at = datetime.utcnow()
    await db.commit()

    return {"message": "Profile updated"}


@router.post("/me/progress-photo")
async def upload_progress_photo(
    file: Optional[UploadFile] = File(None, description="Progress image (form field: file)"),
    image: Optional[UploadFile] = File(None, description="Progress image (form field: image)"),
    face_rating: Optional[float] = Form(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a daily progress picture for the current user.

    Accepts multipart form with either "file" or "image" field.
    The image is stored via the storage service and a record is persisted
    in the user_progress_photos collection for archive display in the app.
    """
    upload = file or image
    if not upload:
        logger.warning("progress-photo: no file or image in request")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing file: send multipart form with 'file' or 'image'",
        )

    content = await upload.read(_MAX_IMAGE_BYTES + 1)
    _validate_image_upload(content, upload.content_type, "Progress photo")
    image_url = await storage_service.upload_image(
        content,
        current_user["id"],
        image_type="progress",
    )
    if not image_url:
        raise HTTPException(status_code=500, detail="Failed to upload progress image")

    fr = face_rating
    if fr is not None and (fr < 0 or fr > 10):
        fr = None

    photo = UserProgressPhoto(
        user_id=UUID(current_user["id"]),
        image_url=image_url,
        created_at=datetime.utcnow(),
        source="app",
        face_rating=fr,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return {
        "photo": {
            "id": str(photo.id),
            "user_id": current_user["id"],
            "image_url": image_url,
            "created_at": photo.created_at,
            "source": "app",
            "face_rating": photo.face_rating,
        }
    }


@router.post("/me/progress-photo/base64")
async def upload_progress_photo_base64(
    body: ProgressPhotoBase64Body,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a progress picture as base64 (e.g. from React Native ImagePicker with base64: true).
    """
    raw = body.image_base64
    if not raw or not raw.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="image_base64 is required")

    # Strip data URL prefix if present
    if "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        content = base64.b64decode(raw)
    except Exception as e:
        logger.warning("progress-photo/base64: b64decode failed %s", e)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid base64 image")

    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty image")
    # content_type isn't available on a base64 body; cap decoded size only.
    _validate_image_upload(content, None, "Progress photo")

    image_url = await storage_service.upload_image(
        content,
        current_user["id"],
        image_type="progress",
    )
    if not image_url:
        raise HTTPException(status_code=500, detail="Failed to upload progress image")

    fr = body.face_rating
    if fr is not None and (fr < 0 or fr > 10):
        fr = None

    photo = UserProgressPhoto(
        user_id=UUID(current_user["id"]),
        image_url=image_url,
        created_at=datetime.utcnow(),
        face_rating=fr,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return {
        "photo": {
            "id": str(photo.id),
            "user_id": current_user["id"],
            "image_url": image_url,
            "created_at": photo.created_at,
            "face_rating": photo.face_rating,
        }
    }


@router.delete("/me/progress-photos/{photo_id}")
async def delete_progress_photo(
    photo_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single progress photo owned by the current user."""
    user_uuid = UUID(current_user["id"])
    photo_uuid = UUID(photo_id)
    result = await db.execute(
        select(UserProgressPhoto)
        .where(UserProgressPhoto.id == photo_uuid, UserProgressPhoto.user_id == user_uuid)
    )
    photo = result.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    try:
        delete_by_url(photo.image_url)
    except Exception as e:
        logger.warning("Progress photo S3 cleanup failed: %s", e)
    await db.execute(
        delete(UserProgressPhoto)
        .where(UserProgressPhoto.id == photo_uuid, UserProgressPhoto.user_id == user_uuid)
    )
    await db.commit()
    return {"message": "Photo deleted"}


@router.get("/me/progress-photos")
async def list_progress_photos(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List recent progress photos for the current user (most recent first).
    """
    limit = min(max(1, limit), 100)  # clamp — don't let a client request unbounded rows
    result = await db.execute(
        select(UserProgressPhoto)
        .where(UserProgressPhoto.user_id == UUID(current_user["id"]))
        .order_by(UserProgressPhoto.created_at.desc())
        .limit(limit)
    )
    photos = result.scalars().all()
    return {"photos": [
        {
            "id": str(p.id),
            "user_id": current_user["id"],
            "image_url": p.image_url,
            "created_at": p.created_at,
            "source": getattr(p, "source", None) or "app",
            "face_rating": getattr(p, "face_rating", None),
        }
        for p in photos
    ]}


def _blocked_ids_list(profile: dict | None) -> list[str]:
    raw = (profile or {}).get("blocked_user_ids")
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if x]


@router.get("/me/blocks")
async def list_blocked_users(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """User IDs the current user has blocked in community channels."""
    user = await db.get(User, UUID(current_user["id"]))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"blocked_user_ids": _blocked_ids_list(user.profile)}


@router.post("/me/blocks")
async def block_user(
    body: BlockUserRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Block a user so their channel messages are hidden for you (App Store Guideline 1.2)."""
    uid = current_user["id"]
    target = body.blocked_user_id.strip()
    if target == uid:
        raise HTTPException(status_code=400, detail="You cannot block yourself")
    try:
        UUID(target)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user id")

    target_user = await db.get(User, UUID(target))
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    user = await db.get(User, UUID(uid))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    prof = dict(user.profile or {})
    blocked = _blocked_ids_list(prof)
    if target not in blocked:
        blocked.append(target)
    prof["blocked_user_ids"] = blocked
    user.profile = prof
    user.updated_at = _utcnow()
    await db.commit()
    return {"blocked_user_ids": blocked}


@router.delete("/me/blocks/{blocked_user_id}")
async def unblock_user(
    blocked_user_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, UUID(current_user["id"]))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    prof = dict(user.profile or {})
    blocked = [x for x in _blocked_ids_list(prof) if x != blocked_user_id]
    prof["blocked_user_ids"] = blocked
    user.profile = prof
    user.updated_at = _utcnow()
    await db.commit()
    return {"blocked_user_ids": blocked}


@router.delete("/me")
async def delete_my_account(
    body: DeleteAccountRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Permanently delete the signed-in account (App Store Guideline 5.1.1)."""
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Google/OAuth-only accounts have a random unusable password_hash and no
    # password the user could enter — requiring one here would make it
    # IMPOSSIBLE for them to delete their account (an App Store 5.1.1(v)
    # rejection). They are already authenticated by a valid JWT, so for those
    # accounts the session itself is sufficient re-auth. Password accounts must
    # still confirm with their password.
    is_oauth_only = str(getattr(user, "auth_provider", "") or "").lower() not in ("", "password") \
        or bool(getattr(user, "google_sub", None))
    if not is_oauth_only:
        if not (body.password or "").strip():
            raise HTTPException(status_code=400, detail="Password is required to delete this account")
        if not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=400, detail="Incorrect password")

    await rds_db.execute(
        update(ChannelMessage)
        .where(ChannelMessage.user_id == user_uuid)
        .values(
            content="[deleted]",
            attachment_url=None,
            attachment_type=None,
            reactions={},
        )
    )
    await rds_db.commit()

    await db.execute(delete(User).where(User.id == user_uuid))
    await db.commit()

    return {"message": "Account deleted"}


@router.put("/account")
async def update_account(
    data: AccountUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update user account info (first_name, last_name, username, phone).
    Phone: set when none on file, or replace while SMS is not yet linked (sendblue_sms_engaged false).
    Note: Email cannot be changed
    """
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_fields = {}

    if data.first_name is not None:
        update_fields["first_name"] = data.first_name.strip() if data.first_name.strip() else None
    if data.last_name is not None:
        update_fields["last_name"] = data.last_name.strip() if data.last_name.strip() else None
    if data.username is not None:
        username_clean = data.username.strip()
        current_username = current_user.get("username") or ""
        username_actually_changed = username_clean.lower() != current_username.lower()

        if username_clean and username_actually_changed:
            last_change = current_user.get("last_username_change")
            if last_change:
                last_utc = _as_utc_aware(last_change)
                cooldown_end = last_utc + timedelta(weeks=2)
                now = _utcnow()
                if now < cooldown_end:
                    seconds_left = (cooldown_end - now).total_seconds()
                    days_left = max(1, math.ceil(seconds_left / 86400))
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"You can only change your username once every 2 weeks. Try again in {days_left} day{'s' if days_left != 1 else ''}."
                    )
            if len(username_clean) < 3:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username must be at least 3 characters"
                )
            if not username_clean.replace('_', '').isalnum():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username can only contain letters, numbers, and underscores"
                )
            result = await db.execute(
                select(User).where(
                    (User.username == username_clean.lower()) &
                    (User.id != UUID(current_user["id"]))
                )
            )
            if result.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already taken"
                )
            update_fields["username"] = username_clean.lower()
            update_fields["last_username_change"] = _utcnow()
        elif not username_clean:
            update_fields["username"] = None

    if data.phone_number is not None:
        existing_digits = re.sub(r"\D", "", (user.phone_number or ""))
        ob = user.onboarding if isinstance(user.onboarding, dict) else {}
        sendblue_sms_engaged = ob.get("sendblue_sms_engaged") is True
        if len(existing_digits) >= 10 and sendblue_sms_engaged:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number is already set on this account.",
            )
        raw = (data.phone_number or "").strip()
        if not raw:
            update_fields["phone_number"] = None
        else:
            normalized = normalize_phone(raw)
            dig = re.sub(r"\D", "", normalized)
            if len(dig) < 10:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Enter a valid phone number with country code.",
                )
            phone_candidates = list(
                dict.fromkeys(phone_lookup_candidates(normalized) + [normalized])
            )
            dup = await db.execute(
                select(User).where(
                    and_(
                        User.phone_number.in_(phone_candidates),
                        User.id != user_uuid,
                    )
                )
            )
            if dup.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Phone number already registered",
                )
            update_fields["phone_number"] = normalized

    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )

    for key, value in update_fields.items():
        setattr(user, key, value)
    user.updated_at = _utcnow()
    await db.commit()
    
    return {"message": "Account updated"}


@router.get("/goals", response_model=List[str])
async def get_available_goals():
    """
    Get list of available improvement goals
    """
    return [goal.value for goal in GoalType]


@router.get("/experience-levels", response_model=List[str])
async def get_experience_levels():
    """
    Get list of experience levels
    """
    return [level.value for level in ExperienceLevel]
