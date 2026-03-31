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

# Strip formal schedule labels so SMS reads like a text, not "Category — time. Body"
_MODULE_TITLE_PREFIX = re.compile(
    r"^(SkinMax|HairMax|HeightMax|BoneMax|FitMax)\s*[\u2014\-–]\s*",
    re.I,
)
_FORMAL_SEGMENT_PREFIX = re.compile(
    r"^(Midday\s+Tip|Hydration\s+Check|SPF\s+Reapply|Weekly\s+Weigh-?in)\s*:\s*",
    re.I,
)


def _strip_schedule_title_labels(title: str) -> str:
    t = (title or "").strip()
    if not t:
        return ""
    t = _MODULE_TITLE_PREFIX.sub("", t)
    t = _FORMAL_SEGMENT_PREFIX.sub("", t)
    return t.strip()


def _trim_sms_body(s: str, max_len: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    cut = s[: max_len - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def _core_text_for_reminder(task_title: str, task_description: str) -> str:
    """Prefer description (the actionable reference); fall back to cleaned title."""
    d = (task_description or "").replace("*", "").strip()
    t = _strip_schedule_title_labels((task_title or "").replace("*", ""))
    if len(d) >= 10:
        return _trim_sms_body(d, 260)
    if d and t:
        if t.lower() in d.lower()[: min(60, len(d))]:
            return _trim_sms_body(d, 260)
        return _trim_sms_body(f"{t}: {d}", 260)
    if t:
        return _trim_sms_body(t, 260)
    return "heads up — you've got this on your list today."


def _lowercase_casual_opening(s: str) -> str:
    """Lowercase sentence case for a text-y vibe; skip product lists / odd casing."""
    s = (s or "").strip()
    if not s:
        return s
    if s[0] in "(0123456789•":
        return s
    m = re.match(r"^([A-Za-z']+)", s)
    if m:
        word = m.group(1)
        caps = sum(1 for c in word if c.isupper())
        if len(word) > 1 and caps > 1 and not word.isupper():
            return s
    if s[0].isalpha() and s[0].isupper() and len(s) > 1 and s[1].islower():
        return s[0].lower() + s[1:]
    return s


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

    def _format_time_12h(self, raw: str) -> str:
        """
        Convert "HH:MM" (24h) -> "h:MMam/pm" for user-facing SMS copy.
        If already contains am/pm or doesn't look like a clock, return as-is.
        """
        s = (raw or "").strip()
        if not s:
            return s
        if re.search(r"\b(am|pm)\b", s, re.I):
            return s
        m = re.match(r"^(\d{1,2}):(\d{2})$", s)
        if not m:
            return s
        try:
            h = int(m.group(1))
            mn = int(m.group(2))
        except ValueError:
            return s
        if h < 0 or h > 23 or mn < 0 or mn > 59:
            return s
        ap = "am" if h < 12 else "pm"
        h12 = h % 12
        if h12 == 0:
            h12 = 12
        return f"{h12}:{mn:02d}{ap}"

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
            f"yo {name}, welcome to max — you're in. "
            f"hop in the app to turn on your programs; ping me here anytime after that."
        )
        return bool(await self.send_sms(phone, msg))

    async def send_scan_complete(
        self,
        phone: str,
        email: str,
        overall_score: float | None,
    ) -> bool:
        score_txt = f"{overall_score:.1f}" if overall_score is not None else "ready"
        msg = (
            f"your scan results are in (~{score_txt}/10 ballpark). "
            f"open max for the full breakdown when you have a sec."
        )
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
        """
        Casual single-line (or short) SMS: no explicit time prefix, reads like a normal reminder text.
        Schedule JSON title/description remain the source of truth in the app; this is delivery tone only.
        """
        core = _lowercase_casual_opening(_core_text_for_reminder(task_title, task_description))
        return _trim_sms_body(core, 300)

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
        n = len(lines)
        intro = "hey — a few things:" if n == 2 else f"hey — {n} things:"
        body = intro + "\n\n" + "\n\n".join(lines)
        if len(body) > 900:
            body = body[:897] + "…"
        return bool(await self.send_sms(phone, body))

    async def send_coaching_sms(self, phone: str, message: str) -> bool:
        return bool(await self.send_sms(phone, message))


sendblue_service = SendblueService()
