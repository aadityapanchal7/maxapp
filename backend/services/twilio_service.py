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

    def _format_schedule_reminder_sms(
        self,
        task_title: str,
        task_description: str,
        task_time: str,
    ) -> str:
        """Plain reminder text from the schedule only — no app/module branding."""
        title = (task_title or "").strip()
        desc = (task_description or "").strip()
        when = (task_time or "").strip()

        if title:
            body = title
        elif desc:
            body = desc.split("\n")[0].split(".")[0].strip()
        elif when:
            body = when
        else:
            body = "Something you put on today's list."

        if when and when.lower() not in body.lower():
            body = f"{body} — {when}"

        # Add a short detail from the description when it's not just repeating the title
        if title and desc:
            first = desc.split(".")[0].strip()
            if (
                first
                and first.lower() != title.lower()
                and not first.lower().startswith(title.lower()[: min(15, len(title))])
            ):
                if len(body) + len(first) + 2 <= 300:
                    body = f"{body}. {first}"

        if len(body) > 300:
            body = body[:297] + "…"
        return body

    async def send_schedule_reminder(
        self,
        phone: str,
        task_title: str,
        task_description: str,
        task_time: str,
    ) -> bool:
        """SMS that reads like a simple schedule reminder — task copy only."""
        message = self._format_schedule_reminder_sms(task_title, task_description, task_time)
        return bool(await self.send_sms(phone, message))

    async def send_schedule_reminder_group(
        self,
        phone: str,
        tasks: list[tuple[dict, str]],
    ) -> bool:
        """
        One SMS for multiple schedule tasks (deduped across active modules).
        tasks: list of (task dict with title/description, original time string).
        """
        if not tasks:
            return False
        if len(tasks) == 1:
            task, ttime = tasks[0]
            return await self.send_schedule_reminder(
                phone,
                task.get("title", "Task"),
                task.get("description", ""),
                ttime,
            )
        lines: list[str] = []
        for task, ttime in tasks:
            line = self._format_schedule_reminder_sms(
                task.get("title", "Task"),
                task.get("description", ""),
                ttime,
            )
            lines.append(line)
        body = f"{len(tasks)} reminders: " + " | ".join(lines)
        if len(body) > 320:
            body = body[:317] + "…"
        return bool(await self.send_sms(phone, body))

    async def send_coaching_sms(self, phone: str, message: str) -> bool:
        """Send an AI-generated coaching check-in via SMS"""
        return bool(await self.send_sms(phone, message))


# Singleton instance
twilio_service = TwilioService()
