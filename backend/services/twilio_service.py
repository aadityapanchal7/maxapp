"""
Twilio Messaging Service - Send SMS and WhatsApp messages via Twilio
"""

import logging
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)


class TwilioService:
    """Handles SMS and WhatsApp messaging via Twilio"""

    def __init__(self):
        self._client = None

    def _get_client(self):
        """Lazy-load Twilio client so missing credentials don't crash startup"""
        if self._client is None:
            if not settings.twilio_account_sid or not settings.twilio_auth_token:
                logger.warning("Twilio credentials not configured - messaging will be disabled")
                return None
            from twilio.rest import Client
            self._client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        return self._client

    def _format_phone(self, phone: str, is_whatsapp: bool = False) -> str:
        """Ensure number is in E.164 format (+XXXXXXXXXXX) or whatsapp: format"""
        # Remove any spaces, dashes, or parentheses
        phone = "".join(filter(str.isdigit, phone.strip()))
        
        # If it's 10 digits, assume it's a US/Canada number and prepend +1
        if len(phone) == 10:
            phone = "+1" + phone
        elif not phone.startswith("+"):
            phone = "+" + phone
        
        if is_whatsapp:
            if not phone.startswith("whatsapp:"):
                phone = f"whatsapp:{phone}"
        return phone

    async def send_sms(self, to_phone: str, message: str) -> Optional[str]:
        """
        Send a standard SMS message to a phone number.
        Returns message SID on success, None on failure.
        """
        if not to_phone:
            return None
        try:
            client = self._get_client()
            if not client:
                return None
            
            from_phone = settings.twilio_sms_from
            if not from_phone:
                logger.warning("TWILIO_SMS_FROM not configured")
                return None

            msg = client.messages.create(
                from_=from_phone,
                to=self._format_phone(to_phone),
                body=message
            )
            logger.info(f"SMS sent to {to_phone} (SID: {msg.sid})")
            return msg.sid
        except Exception as e:
            logger.error(f"SMS send failed to {to_phone}: {e}")
            return None

    async def send_whatsapp(self, to_phone: str, message: str) -> Optional[str]:
        """
        Send a WhatsApp message to a phone number.
        Returns message SID on success, None on failure.
        """
        if not to_phone:
            return None
        try:
            client = self._get_client()
            if not client:
                return None

            msg = client.messages.create(
                from_=settings.twilio_whatsapp_from,
                to=self._format_phone(to_phone, is_whatsapp=True),
                body=message
            )
            logger.info(f"WhatsApp sent to {to_phone} (SID: {msg.sid})")
            return msg.sid
        except Exception as e:
            logger.error(f"WhatsApp send failed to {to_phone}: {e}")
            return None

    async def send_welcome(self, phone: str, email: str) -> bool:
        """Welcome message sent after successful signup"""
        name = email.split("@")[0].capitalize()
        message = (
            f"👋 Welcome to *Max*, {name}!\n\n"
            f"You're now part of the Max community — the #1 looksmaxxing platform.\n\n"
            f"🎯 Complete your first face scan to get your personal analysis and score.\n\n"
            f"Let's get started! 🚀"
        )
        return bool(await self.send_whatsapp(phone, message))

    async def send_scan_complete(self, phone: str, email: str, overall_score: Optional[float]) -> bool:
        """Notification sent after a face scan analysis completes"""
        name = email.split("@")[0].capitalize()
        score_text = f"*{overall_score:.1f}/10*" if overall_score is not None else "ready"
        message = (
            f"✅ Hey {name}, your Max face scan is complete!\n\n"
            f"📊 Your overall score: {score_text}\n\n"
            f"Open the Max app to see your full analysis and personalized recommendations. 💪"
        )
        return bool(await self.send_whatsapp(phone, message))

    async def send_schedule_reminder(self, phone: str, task_title: str, task_description: str, task_time: str) -> bool:
        """Send a WhatsApp reminder for a scheduled task"""
        message = (
            f"⏰ *Max Reminder* — {task_time}\n\n"
            f"💪 *{task_title}*\n"
            f"{task_description}\n\n"
            f"Open the app to mark it done! ✅"
        )
        return bool(await self.send_whatsapp(phone, message))

    async def send_daily_progress_prompt(self, phone: str, name: str | None = None) -> bool:
        """Send a WhatsApp prompt asking the user for a daily progress picture"""
        display_name = (name or "").split("@")[0].capitalize() if name else ""
        greeting = f"Hey {display_name}," if display_name else "Hey,"
        message = (
            f"📸 {greeting} it's time for your daily progress check-in.\n\n"
            f"Send a quick progress picture so Max can track your journey over time.\n\n"
            f"Open the Max app to upload it to your private archive. 🔒"
        )
        return bool(await self.send_whatsapp(phone, message))


# Singleton instance
twilio_service = TwilioService()
