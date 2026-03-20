"""
Authentication Middleware - JWT token verification
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from db import get_db
from models.sqlalchemy_models import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Verify JWT token and return current user
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if user_id is None or token_type != "access":
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
    
    # Get user from database
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "created_at": user.created_at,
        "is_paid": user.is_paid,
        "is_admin": user.is_admin,
        "subscription_status": user.subscription_status,
        "subscription_id": user.subscription_id,
        "subscription_end_date": user.subscription_end_date,
        "stripe_customer_id": user.stripe_customer_id,
        "onboarding": user.onboarding or {},
        "profile": user.profile or {},
        "first_scan_completed": user.first_scan_completed,
        "phone_number": user.phone_number,
        "last_username_change": user.last_username_change,
        "schedule_preferences": user.schedule_preferences or {},
        "last_progress_prompt_date": user.last_progress_prompt_date,
    }


async def get_current_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Verify user is an admin
    """
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_optional_user(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[dict]:
    """
    Get current user if token is provided, otherwise return None
    """
    if not token:
        return None
    
    try:
        return await get_current_user(token)
    except HTTPException:
        return None


async def require_paid_user(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Verify user has active subscription (admins are always allowed)
    """
    if current_user.get("is_admin", False):
        return current_user
        
    if not current_user.get("is_paid", False):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required"
        )
    
    # Check subscription end date
    sub_end = current_user.get("subscription_end_date")
    if sub_end and isinstance(sub_end, datetime):
        if sub_end < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Subscription has expired"
            )
    
    return current_user
