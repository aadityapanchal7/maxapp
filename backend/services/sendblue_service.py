"""
Sendblue Messaging — iMessage / SMS (replaces Twilio for outbound + webhook-driven replies).
API: https://docs.sendblue.com/
"""

import logging
import re
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

SENDBLUE_API = "https://api.sendblue.co/api"


def onboarding_allows_proactive_sms(onboarding: dict | None) -> bool:
    """Schedule reminders, scan-complete texts, coaching nudges — only after user has texted our line."""
    return (onboarding or {}).get("sendblue_sms_engaged") is True


def normalize_phone(phone: str) -> str:
    """Normalize to E.164 (+XXXXXXXXXXX)."""
    digits = re.sub(r"[^\d+]", "", (phone or "").strip())
    if not digits.startswith("+"):
        digits = re.sub(r"[^\d]", "", digits)
        if len(digits) == 10:
            digits = "+1" + digits
        else:
            digits = "+" + digits
    return digits


def phone_lookup_candidates(raw_from: str) -> list[str]:
    """Possible DB phone strings for matching inbound Sendblue `number` / `from_number`."""
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


class SendblueService:
    """Outbound messages via Sendblue REST API."""

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "sb-api-key-id": settings.sendblue_api_key_id,
            "sb-api-secret-key": settings.sendblue_api_secret_key,
        }

    def _configured(self) -> bool:
        return bool(
            settings.sendblue_api_key_id
            and settings.sendblue_api_secret_key
            and settings.sendblue_from_number
        )

    async def send_message(
        self,
        to_phone: str,
        content: str,
        *,
        media_url: Optional[str] = None,
        status_callback: Optional[str] = None,
    ) -> Optional[str]:
        """
        POST /send-message. Returns message_handle on success, None on failure.
        Requires content and/or media_url per API.
        """
        if not to_phone or not self._configured():
            if not self._configured():
                logger.warning("Sendblue not configured — skip send")
            return None
        to_e164 = normalize_phone(to_phone)
        from_e164 = normalize_phone(settings.sendblue_from_number)
        body: dict = {"number": to_e164, "from_number": from_e164}
        if content and content.strip():
            body["content"] = content.strip()
        if media_url:
            body["media_url"] = media_url
        if not body.get("content") and not body.get("media_url"):
            logger.warning("Sendblue send requires content or media_url")
            return None
        if status_callback:
            body["status_callback"] = status_callback

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post(
                    f"{SENDBLUE_API}/send-message",
                    json=body,
                    headers=self._headers(),
                )
            if r.status_code >= 400:
                logger.error(
                    "Sendblue send failed status=%s body=%s",
                    r.status_code,
                    (r.text or "")[:500],
                )
                return None
            data = r.json() if r.text else {}
            handle = data.get("message_handle") or data.get("data", {}).get("message_handle")
            logger.info("Sendblue sent to %s handle=%s", to_e164, handle)
            return str(handle) if handle else "ok"
        except Exception as e:
            logger.error("Sendblue send error: %s", e, exc_info=True)
            return None

    async def send_sms(self, to_phone: str, message: str) -> Optional[str]:
        """Same as send_message with text only (SMS/iMessage)."""
        return await self.send_message(to_phone, message)

    async def send_welcome(self, phone: str, first_name: str | None = None) -> bool:
        name = first_name or "there"
        msg = (
            f"welcome to max, {name}! you're subscribed. "
            f"text us anytime at this number for coaching (iMessage/SMS). "
            f"open the app to pick your programs and dive in."
        )
        return bool(await self.send_sms(phone, msg))

    async def send_scan_complete(
        self,
        phone: str,
        email: str,
        overall_score: float | None,
    ) -> bool:
        score_txt = f"{overall_score:.1f}" if overall_score is not None else "ready"
        msg = f"max: your facial scan rating is in ({score_txt}/10 area). open the app for your full breakdown."
        return bool(await self.send_sms(phone, msg))

    async def send_whatsapp(self, phone: str, message: str) -> bool:
        """Admin/test helper — Sendblue delivers iMessage/SMS, not WhatsApp."""
        return bool(await self.send_sms(phone, message))

    def _format_schedule_reminder_sms(
        self,
        task_title: str,
        task_description: str,
        task_time: str,
    ) -> str:
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
        message = self._format_schedule_reminder_sms(task_title, task_description, task_time)
        return bool(await self.send_sms(phone, message))

    async def send_schedule_reminder_group(
        self,
        phone: str,
        tasks: list[tuple[dict, str]],
    ) -> bool:
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
        return bool(await self.send_sms(phone, message))


sendblue_service = SendblueService()
