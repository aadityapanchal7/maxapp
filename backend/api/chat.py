"""
Chat API - Cannon LLM Chat
"""

from fastapi import APIRouter, Depends
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db
from middleware.auth_middleware import require_paid_user
from services.gemini_service import gemini_service
from services.storage_service import storage_service
from models.leaderboard import ChatRequest, ChatResponse
from models.sqlalchemy_models import ChatHistory, Scan

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/message", response_model=ChatResponse)
async def send_message(
    data: ChatRequest,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Send message to Cannon AI"""
    from services.schedule_service import schedule_service
    user_id = current_user["id"]
    user_uuid = UUID(user_id)
    
    # Get chat history
    history_result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user_uuid)
        .order_by(ChatHistory.created_at.desc())
        .limit(50)
    )
    history_rows = list(reversed(history_result.scalars().all()))
    history = [
        {
            "role": h.role,
            "content": h.content,
            "attachment_url": None,
            "attachment_type": None,
            "created_at": h.created_at
        }
        for h in history_rows
    ]
    
    # Get active schedule for context
    active_schedule = await schedule_service.get_current_schedule(user_id, db=db)
    
    # Get user context
    latest_scan_result = await db.execute(
        select(Scan).where(Scan.user_id == user_uuid).order_by(Scan.created_at.desc()).limit(1)
    )
    latest_scan = latest_scan_result.scalar_one_or_none()
    user_context = {
        "latest_scan": latest_scan.analysis if latest_scan else None,
        "active_schedule": active_schedule
    }
    
    # Get attachment data if it's an image
    image_data = None
    if data.attachment_url and data.attachment_type == "image":
        image_data = await storage_service.get_image(data.attachment_url)
    
    # Get response from Gemini
    result = await gemini_service.chat(data.message, history, user_context, image_data)
    response_text = result.get("text", "")
    tool_calls = result.get("tool_calls", [])
    
    # Handle tools
    for tool in tool_calls:
        if tool["name"] == "modify_schedule" and active_schedule:
            try:
                feedback = tool["args"].get("feedback")
                if feedback:
                    await schedule_service.adapt_schedule(
                        user_id=user_id,
                        schedule_id=active_schedule["id"],
                        db=db,
                        feedback=feedback
                    )
                    # We could optionally add a notice to the response or refresh the context
            except Exception as e:
                print(f"Chat-triggered schedule adaptation failed: {e}")
    
    # Save to history
    user_message = ChatHistory(
        user_id=user_uuid,
        role="user",
        content=data.message,
        created_at=datetime.utcnow()
    )
    assistant_message = ChatHistory(
        user_id=user_uuid,
        role="assistant",
        content=response_text,
        created_at=datetime.utcnow()
    )
    db.add(user_message)
    db.add(assistant_message)
    await db.commit()
    
    return ChatResponse(response=response_text)


@router.get("/history")
async def get_chat_history(
    limit: int = 50,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Get chat history"""
    user_uuid = UUID(current_user["id"])
    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user_uuid)
        .order_by(ChatHistory.created_at.desc())
        .limit(limit)
    )
    rows = list(reversed(result.scalars().all()))
    return {"messages": [
        {"role": r.role, "content": r.content, "created_at": r.created_at}
        for r in rows
    ]}
