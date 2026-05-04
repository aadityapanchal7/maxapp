"""
Notifications API — admin / test outbound messages via Sendblue (iMessage/SMS).
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from middleware import get_current_user
from middleware.auth_middleware import get_current_admin_user
from services.sendblue_service import sendblue_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class SendMessageRequest(BaseModel):
    phone: str
    message: str


class TestMessageRequest(BaseModel):
    phone: str


@router.post("/send")
async def send_whatsapp_message(
    request: SendMessageRequest,
    current_user: dict = Depends(get_current_admin_user)
):
    """Admin: send a custom text to any number (Sendblue iMessage/SMS)."""
    success = await sendblue_service.send_whatsapp(request.phone, request.message)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to send message. Check Sendblue API keys and SENDBLUE_FROM_NUMBER.",
        )
    return {"success": True, "message": "Message sent"}


@router.post("/test")
async def send_test_message(
    request: TestMessageRequest,
    current_user: dict = Depends(get_current_user)
):
    """Send a test message to verify Sendblue is working."""
    success = await sendblue_service.send_whatsapp(
        request.phone,
        "🧪 Test from Agartha — Sendblue iMessage/SMS is connected. ✅",
    )
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to send. Check Sendblue credentials and that the recipient can receive iMessage/SMS.",
        )
    return {"success": True, "message": "Test message sent"}
