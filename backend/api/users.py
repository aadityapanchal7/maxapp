"""
Users API - Profile and Onboarding
"""

from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File
from datetime import datetime
from typing import List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from middleware.auth_middleware import get_current_user
from services.storage_service import storage_service
from models.user import (
    UserResponse, OnboardingData, UserProfile, GoalType, ExperienceLevel
)
from models.sqlalchemy_models import User

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_profile(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's profile
    """
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=str(user.id),
        email=user.email,
        created_at=user.created_at,
        is_paid=user.is_paid,
        subscription_status=user.subscription_status,
        subscription_end_date=user.subscription_end_date,
        onboarding=OnboardingData(**user.onboarding) if user.onboarding else OnboardingData(),
        profile=UserProfile(**user.profile) if user.profile else UserProfile(),
        first_scan_completed=user.first_scan_completed,
        is_admin=user.is_admin
    )


@router.post("/onboarding")
async def save_onboarding(
    data: OnboardingData,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
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


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload profile picture
    """
    user_uuid = UUID(current_user["id"])
    user = await db.get(User, user_uuid)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Read file content
    content = await file.read()
    
    # Upload to storage
    avatar_url = await storage_service.upload_image(
        content,
        str(user_uuid),
        image_type="avatar"
    )
    
    if not avatar_url:
        raise HTTPException(status_code=500, detail="Failed to upload image")
    
    # Update user profile
    if not user.profile:
        user.profile = {}
    user.profile["avatar_url"] = avatar_url
    user.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return {"avatar_url": avatar_url}


@router.put("/profile")
async def update_profile(
    profile: UserProfile,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
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
    current_profile.update(updated_data)

    user.profile = current_profile
    user.updated_at = datetime.utcnow()
    await db.commit()

    return {"message": "Profile updated", "profile": user.profile}


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
