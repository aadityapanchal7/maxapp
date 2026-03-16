"""
Chat API - Cannon LLM Chat
Handles AI chat with tool-calling for schedule management.
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
from models.sqlalchemy_models import ChatHistory, Scan, User

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
            "created_at": h.created_at,
        }
        for h in history_rows
    ]

    active_schedule = await schedule_service.get_current_schedule(user_id, db=db)

    user = await db.get(User, user_uuid)
    onboarding = (user.onboarding if user else {}) or {}

    latest_scan_result = await db.execute(
        select(Scan).where(Scan.user_id == user_uuid).order_by(Scan.created_at.desc()).limit(1)
    )
    latest_scan = latest_scan_result.scalar_one_or_none()

    user_context = {
        "latest_scan": latest_scan.analysis if latest_scan else None,
        "active_schedule": active_schedule,
        "onboarding": onboarding,
    }

    # If init_context is set, prepend context to the message so Cannon knows
    message = data.message
    if data.init_context:
        maxx_id = data.init_context
        try:
            existing_maxx = await schedule_service.get_maxx_schedule(user_id, maxx_id, db=db)
        except Exception:
            existing_maxx = None
        if existing_maxx:
            user_context["active_maxx_schedule"] = existing_maxx
            message = f"[SYSTEM: User opened the {maxx_id} module and already has an active schedule. They may want to view or update it.]\n\n{message}"
        else:
            message = f"[SYSTEM: User just tapped 'Start Schedule' in the {maxx_id} module. Begin the schedule onboarding flow — ask their wake time, sleep time, and whether they'll be outside. Ask one question at a time.]\n\n{message}"

    image_data = None
    if data.attachment_url and data.attachment_type == "image":
        image_data = await storage_service.get_image(data.attachment_url)

    result = await gemini_service.chat(message, history, user_context, image_data)
    response_text = result.get("text", "")
    tool_calls = result.get("tool_calls", [])

    for tool in tool_calls:
        if tool["name"] == "modify_schedule" and active_schedule:
            try:
                feedback = tool["args"].get("feedback")
                if feedback:
                    await schedule_service.adapt_schedule(
                        user_id=user_id,
                        schedule_id=active_schedule["id"],
                        db=db,
                        feedback=feedback,
                    )
            except Exception as e:
                print(f"Chat-triggered schedule adaptation failed: {e}")

        elif tool["name"] == "generate_maxx_schedule":
            try:
                args = tool["args"]
                schedule = await schedule_service.generate_maxx_schedule(
                    user_id=user_id,
                    maxx_id=str(args.get("maxx_id", "skinmax")),
                    db=db,
                    wake_time=str(args.get("wake_time", "07:00")),
                    sleep_time=str(args.get("sleep_time", "23:00")),
                    skin_concern=onboarding.get("skin_type"),
                    outside_today=bool(args.get("outside_today", False)),
                )
                schedule_summary = _summarise_schedule(schedule)
                if not response_text.strip():
                    response_text = schedule_summary
                else:
                    response_text += f"\n\n{schedule_summary}"
            except Exception as e:
                print(f"Chat-triggered maxx schedule generation failed: {e}")
                response_text += f"\n\nSorry, I had trouble generating your schedule. Try again in a moment."

        elif tool["name"] == "update_schedule_context":
            try:
                args = tool["args"]
                key = str(args.get("key", ""))
                value = str(args.get("value", ""))
                if active_schedule and key:
                    await schedule_service.update_schedule_context(
                        user_id=user_id,
                        schedule_id=active_schedule["id"],
                        db=db,
                        context_updates={key: value},
                    )
            except Exception as e:
                print(f"Chat-triggered context update failed: {e}")

    user_message = ChatHistory(
        user_id=user_uuid,
        role="user",
        content=data.message,
        created_at=datetime.utcnow(),
    )
    assistant_message = ChatHistory(
        user_id=user_uuid,
        role="assistant",
        content=response_text,
        created_at=datetime.utcnow(),
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
    # If user wants skinmax and hasn't set it up, seed the conversation
    user = await db.get(User, user_uuid)
    goals = (user.onboarding or {}).get("goals", []) if user else []
    skin = (user.schedule_preferences or {}).get("skinmax", {}) if user else {}

    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user_uuid)
        .order_by(ChatHistory.created_at.desc())
        .limit(limit)
    )
    rows = list(reversed(result.scalars().all()))
    return {
        "messages": [
            {"role": r.role, "content": r.content, "created_at": r.created_at}
            for r in rows
        ]
    }


def _summarise_schedule(schedule: dict) -> str:
    """Build a human-readable summary of a generated schedule."""
    days = schedule.get("days", [])
    if not days:
        return "Your schedule has been created!"

    first_day = days[0]
    tasks = first_day.get("tasks", [])
    lines = [f"Your {schedule.get('course_title', 'schedule')} is ready! Here's Day 1:"]
    for t in tasks[:6]:
        lines.append(f"  {t.get('time', '??:??')} — {t.get('title', 'Task')}")
    if len(tasks) > 6:
        lines.append(f"  ... and {len(tasks) - 6} more tasks")
    lines.append(f"\nTotal: {len(days)} days planned. Check your Schedule tab to see everything!")
    return "\n".join(lines)
