"""
Twilio Messaging Service - SMS notifications and chatbot replies
"""

import re
import logging
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> str:
    """Normalize a phone number to E.164 format (+XXXXXXXXXXX) for consistent storage and lookup."""
    digits = re.sub(r"[^\d+]", "", phone.strip())
    if not digits.startswith("+"):
        digits = re.sub(r"[^\d]", "", digits)
        if len(digits) == 10:
            digits = "+1" + digits
        else:
            digits = "+" + digits
    return digits


class TwilioService:
    """Handles SMS messaging via Twilio"""

    def __init__(self):
        self._client = None

    def _get_client(self):
        """Lazy-load Twilio client. Re-checks credentials each time until they're found."""
        if self._client is not None:
            return self._client
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            logger.warning("Twilio credentials not configured - messaging will be disabled")
            return None
        from twilio.rest import Client
        self._client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        return self._client

    async def send_sms(self, to_phone: str, message: str) -> Optional[str]:
        """
        Send an SMS message to a phone number.
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
                to=normalize_phone(to_phone),
                body=message,
            )
            logger.info(f"SMS sent to {to_phone} (SID: {msg.sid})")
            return msg.sid
        except Exception as e:
            logger.error(f"SMS send failed to {to_phone}: {e}")
            return None

    async def send_welcome(self, phone: str, email: str) -> bool:
        """Welcome SMS sent after payment activation (or dev skip)"""
        name = email.split("@")[0].capitalize()
        message = (
            f"welcome to max, {name}! "
            f"you're all set — your subscription is active. "
            f"open the app, do your first face scan, and let's get started."
        )
        return bool(await self.send_sms(phone, message))

    async def send_schedule_reminder(self, phone: str, task_title: str, task_description: str, task_time: str) -> bool:
        """Send an SMS reminder for a scheduled task"""
        desc = f" - {task_description}" if task_description else ""
        message = f"max reminder ({task_time}): {task_title}{desc}. open the app to mark it done."
        return bool(await self.send_sms(phone, message))

    async def send_daily_progress_prompt(self, phone: str, name: str | None = None) -> bool:
        """Send an SMS prompt asking the user for a daily progress picture"""
        display_name = (name or "").split("@")[0].capitalize() if name else ""
        greeting = f"hey {display_name}," if display_name else "hey,"
        message = f"{greeting} time for your daily progress check-in. open the max app to upload a pic."
        return bool(await self.send_sms(phone, message))

    async def send_coaching_sms(self, phone: str, message: str) -> bool:
        """Send an AI-generated coaching check-in via SMS"""
        return bool(await self.send_sms(phone, message))


# Singleton instance
twilio_service = TwilioService()
