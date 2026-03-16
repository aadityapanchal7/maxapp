"""
Admin API - Administrative management endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from db import get_db, get_rds_db
from middleware.auth_middleware import get_current_admin_user
from models.user import UserResponse, OnboardingData, UserProfile
from models.sqlalchemy_models import User, ChatHistory
from models.rds_models import Forum, ChannelMessage


class BroadcastRequest(BaseModel):
    content: str


class DirectMessageRequest(BaseModel):
    user_id: str
    content: str


class AdminChatMessage(BaseModel):
    message: str


router = APIRouter(prefix="/admin", tags=["Admin"])


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        created_at=user.created_at,
        is_paid=user.is_paid,
        subscription_status=user.subscription_status,
        subscription_end_date=user.subscription_end_date,
        onboarding=OnboardingData(**user.onboarding) if user.onboarding else OnboardingData(),
        profile=UserProfile(**user.profile) if user.profile else UserProfile(),
        first_scan_completed=user.first_scan_completed,
        is_admin=user.is_admin,
        phone_number=user.phone_number
    )


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    q: Optional[str] = None,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List all users with pagination and search (Admin only)"""
    query = select(User)
    if q:
        query = query.where(User.email.ilike(f"%{q}%"))

    query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()

    return [_user_to_response(u) for u in users]


@router.get("/stats")
async def get_stats(
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Get high-level system stats"""
    user_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    paid_count = (await db.execute(
        select(func.count(User.id)).where(User.is_paid == True)
    )).scalar() or 0
    channel_count = (await rds_db.execute(select(func.count(Forum.id)))).scalar() or 0
    message_count = (await rds_db.execute(select(func.count(ChannelMessage.id)))).scalar() or 0

    return {
        "total_users": user_count,
        "paid_users": paid_count,
        "total_channels": channel_count,
        "total_messages": message_count
    }


@router.post("/broadcast")
async def broadcast_message(
    data: BroadcastRequest,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a message to ALL users in their Max AI chat"""
    result = await db.execute(select(User.id))
    user_ids = result.scalars().all()

    count = 0
    for user_id in user_ids:
        db.add(ChatHistory(
            user_id=user_id,
            role="assistant",
            content=f"[BROADCAST] {data.content}",
            created_at=datetime.utcnow()
        ))
        count += 1

    await db.commit()
    return {"message": f"Broadcast sent to {count} users"}


@router.post("/direct")
async def direct_message(
    data: DirectMessageRequest,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a direct message to a specific user as Max"""
    try:
        user_uuid = UUID(data.user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.add(ChatHistory(
        user_id=user_uuid,
        role="assistant",
        content=data.content,
        created_at=datetime.utcnow()
    ))
    await db.commit()

    return {"status": "Message sent"}


# ----- Admin ↔ User Chat (as Max) -----

@router.get("/users/{user_id}/chat")
async def get_user_chat(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a user's Max chat history (admin only)"""
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user_uuid)
        .order_by(ChatHistory.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()

    return {
        "user_id": user_id,
        "email": user.email,
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in reversed(messages)
        ]
    }


@router.post("/users/{user_id}/chat")
async def send_user_chat(
    user_id: str,
    data: AdminChatMessage,
    admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a message to a user's Max chat as the assistant (admin only)"""
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_msg = ChatHistory(
        user_id=user_uuid,
        role="assistant",
        content=data.message,
        created_at=datetime.utcnow()
    )
    db.add(new_msg)
    await db.commit()

    return {
        "status": "Message sent",
        "message": {
            "role": new_msg.role,
            "content": new_msg.content,
            "created_at": new_msg.created_at
        }
    }
