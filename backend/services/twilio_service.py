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


def phone_lookup_candidates(raw_from: str) -> list[str]:
    """
    Build possible DB values Twilio might match. Twilio sends e.g. +15551234567;
    users may have stored spaces, missing +1, or 10-digit local only.
    """
    raw = (raw_from or "").strip()
    if not raw:
        return []
    n = normalize_phone(raw)
    digits = re.sub(r"\D", "", raw)
    candidates = [n, raw]
    if len(digits) == 11 and digits.startswith("1"):
        candidates.extend(["+" + digits, digits[1:]])
    if len(digits) == 10:
        candidates.extend(["+1" + digits, digits])
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


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

    async def send_welcome(self, phone: str, first_name: str | None = None) -> bool:
        """Welcome SMS sent after payment activation (or dev skip)"""
        name = first_name or "there"
        message = (
            f"welcome to max, {name}! "
            f"you're all set — your subscription is active. "
            f"open the app, select your modules, and let's get started."
        )
        return bool(await self.send_sms(phone, message))

    async def send_schedule_reminder(
        self, phone: str, task_title: str, task_description: str, task_time: str
    ) -> bool:
        """
        Send an SMS nudge that a schedule item is due.
        Body is intentionally generic: no "max reminder" label, no clock time, no task/module title
        (caller's task_* args are ignored for message copy).
        """
        message = "open the max app to check your schedule and mark tasks done."
        return bool(await self.send_sms(phone, message))

    async def send_coaching_sms(self, phone: str, message: str) -> bool:
        """Send an AI-generated coaching check-in via SMS"""
        return bool(await self.send_sms(phone, message))


# Singleton instance
twilio_service = TwilioService()
