"""
Users API - Profile and Onboarding
"""

import base64
import logging
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)

from db import get_db
from middleware import get_current_user
from services.storage_service import storage_service
from models.user import (
    UserResponse, OnboardingData, UserProfile, GoalType, ExperienceLevel, AccountUpdateRequest
)
from models.sqlalchemy_models import User, UserProgressPhoto

router = APIRouter(prefix="/users", tags=["Users"])


class ProgressPhotoBase64Body(BaseModel):
    """Request body for progress photo upload via base64 (avoids multipart issues on RN)."""
    image_base64: str


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
        created_at=current_user["created_at"],
        is_paid=current_user.get("is_paid", False),
        subscription_status=current_user.get("subscription_status"),
        subscription_end_date=current_user.get("subscription_end_date"),
        onboarding=OnboardingData(**current_user.get("onboarding", {})),
        profile=UserProfile(**current_user.get("profile", {})),
        first_scan_completed=current_user.get("first_scan_completed", False),
        is_admin=current_user.get("is_admin", False),
        phone_number=current_user.get("phone_number")
    )


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

    # Update onboarding data
    onboarding_data = data.model_dump()
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
    # Read file content
    content = await file.read()
    
    # Upload to storage
    avatar_url = await storage_service.upload_image(
        content,
        current_user["id"],
        image_type="avatar"
    )
    
    if not avatar_url:
        raise HTTPException(status_code=500, detail="Failed to upload image")
    
    # Update user profile
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Assign a new dict to ensure SQLAlchemy tracks JSON changes
    current_profile = user.profile or {}
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
    current_profile = user.profile or {}
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

    photo = UserProgressPhoto(
        user_id=UUID(current_user["id"]),
        image_url=image_url,
        created_at=datetime.utcnow(),
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return {"photo": {"id": str(photo.id), "user_id": current_user["id"], "image_url": image_url, "created_at": photo.created_at}}


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

    photo = UserProgressPhoto(
        user_id=UUID(current_user["id"]),
        image_url=image_url,
        created_at=datetime.utcnow(),
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return {"photo": {"id": str(photo.id), "user_id": current_user["id"], "image_url": image_url, "created_at": photo.created_at}}


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
        {"id": str(p.id), "user_id": current_user["id"], "image_url": p.image_url, "created_at": p.created_at}
        for p in photos
    ]}


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
        if username_clean:
            # Validate username format
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
            # Check if username is already taken by another user
            result = await db.execute(
                select(User).where(
                    (User.username == username_clean.lower()) &
                    (User.id != UUID(current_user["id"]))
                )
            )
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already taken"
                )
            update_fields["username"] = username_clean.lower()
        else:
            update_fields["username"] = None
    
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )
    
    update_fields["updated_at"] = datetime.utcnow()
    
    user = await db.get(User, UUID(current_user["id"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    for key, value in update_fields.items():
        setattr(user, key, value)
    user.updated_at = datetime.utcnow()
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
