"""
Notifications API - WhatsApp messaging via Twilio
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from middleware import get_current_user
from middleware.auth_middleware import get_current_admin_user
from services.twilio_service import twilio_service

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
    """Admin: send a custom WhatsApp message to any number"""
    success = await twilio_service.send_whatsapp(request.phone, request.message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send WhatsApp message. Check Twilio credentials and that the number has opted into your sandbox.")
    return {"success": True, "message": "WhatsApp message sent"}


@router.post("/test")
async def send_test_message(
    request: TestMessageRequest,
    current_user: dict = Depends(get_current_user)
):
    """Send a test WhatsApp message to verify Twilio is working"""
    success = await twilio_service.send_whatsapp(
        request.phone,
        "🧪 Test message from Max! Your WhatsApp notifications are working correctly. ✅"
    )
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to send. Make sure the number has joined the Twilio Sandbox by sending 'join <keyword>' to +14155238886 on WhatsApp."
        )
    return {"success": True, "message": "Test WhatsApp sent successfully"}
