"""
Chat API - Cannon LLM Chat
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from db import get_db
from middleware.auth_middleware import require_paid_user
from services.gemini_service import gemini_service
from services.storage_service import storage_service
from models.sqlalchemy_models import ChatHistory, Scan

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/message")
async def send_message(
    data: dict = None,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db)
):
    """Send message to Cannon AI"""
    if data is None:
        data = {}

    user_uuid = UUID(current_user["id"])

    # Get chat history
    history_result = await db.execute(
        select(ChatHistory).where(ChatHistory.user_id == user_uuid)
    )
    history_records = history_result.scalars().all()
    history = [
        {
            "role": record.role,
            "content": record.content,
            "created_at": record.created_at
        }
        for record in history_records[-20:]  # Keep last 20 messages
    ]

    # Get user context from latest scan
    latest_scan_result = await db.execute(
        select(Scan)
        .where(Scan.user_id == user_uuid)
        .order_by(Scan.created_at.desc())
        .limit(1)
    )
    latest_scan = latest_scan_result.scalar_one_or_none()
    user_context = {"latest_scan": latest_scan.analysis if latest_scan else None}

    # Get attachment data if it's an image
    image_data = None
    if data.get("attachment_url") and data.get("attachment_type") == "image":
        image_data = await storage_service.get_image(data["attachment_url"])

    # Get response from Gemini
    message_text = data.get("message", "")
    response_text = await gemini_service.chat(message_text, history, user_context, image_data)

    # Save user message to history
    user_message = ChatHistory(
        user_id=user_uuid,
        role="user",
        content=message_text
    )
    db.add(user_message)
    await db.commit()

    # Save assistant response to history
    assistant_message = ChatHistory(
        user_id=user_uuid,
        role="assistant",
        content=response_text
    )
    db.add(assistant_message)
    await db.commit()

    return {"response": response_text}


@router.get("/history")
async def get_chat_history(
    limit: int = 50,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db)
):
    """Get chat history"""
    user_uuid = UUID(current_user["id"])

    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user_uuid)
        .order_by(ChatHistory.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()

    return {"messages": [
        {
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at
        }
        for msg in reversed(messages)  # Reverse to show chronological order
    ]}
