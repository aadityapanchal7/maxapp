"""
Users API - Profile and Onboarding
"""

import base64
import logging
import math
import re
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Request, Form
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pydantic import BaseModel, Field
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Timezone-aware UTC now for TIMESTAMPTZ columns (asyncpg-safe)."""
    return datetime.now(timezone.utc)


def _as_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


from db import get_db, get_rds_db
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
)
from models.sqlalchemy_models import User, UserProgressPhoto
from models.rds_models import ChannelMessage
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


@router.get("/me", response_model=UserResponse)
async def get_profile(current_user: dict = Depends(get_current_user)):
    """
    Get current user's profile
    """
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
        onboarding=OnboardingData(**current_user.get("onboarding", {})),
        profile=UserProfile(**current_user.get("profile", {})),
        first_scan_completed=current_user.get("first_scan_completed", False),
        is_admin=current_user.get("is_admin", False),
        phone_number=current_user.get("phone_number"),
        has_apns_token=current_user.get("has_apns_token", False),
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
    from services.apns_service import send_apns_alert, apns_configured

    if not apns_configured():
        raise HTTPException(status_code=503, detail="Push notifications are not configured on this server")
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    token = (user.apns_device_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="No push token registered for this device. Make sure notifications are enabled.")
    ok, status_code = await send_apns_alert(
        token,
        "Max",
        "Push notifications are working! You're all set.",
        badge=1,
    )
    if not ok:
        raise HTTPException(status_code=502, detail=f"APNs delivery failed (status {status_code}). Token may be expired.")
    return {"message": "Test notification sent"}


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
    onboarding_data["completed"] = True
    user.onboarding = onboarding_data
    user.updated_at = datetime.utcnow()
    await db.commit()
    
    return {"message": "Onboarding completed", "data": onboarding_data}


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


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload profile picture
    """
    content = await file.read()

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

    content = await upload.read()
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
    Update user account info (first_name, last_name, username)
    Note: Email cannot be changed
    """
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
    
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )

    user = await db.get(User, UUID(current_user["id"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

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
