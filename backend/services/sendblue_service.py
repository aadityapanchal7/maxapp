"""
Sendblue Messaging — iMessage / SMS (replaces Twilio for outbound + webhook-driven replies).
API: https://docs.sendblue.com/
"""

import logging
import re
from typing import Optional

import httpx

from config import settings
from services.copy_filter import filter_text

logger = logging.getLogger(__name__)

SENDBLUE_API = "https://api.sendblue.co/api"

# Strip formal schedule labels so SMS reads like a text, not "Category — time. Body"


def onboarding_allows_proactive_sms(onboarding: dict | None) -> bool:
    """Schedule reminders, scan-complete texts, coaching nudges — only after user has texted our line."""
    ob = onboarding or {}
    # Default to SMS on for backwards compatibility; opt-out is only meaningful when explicitly disabled.
    sms_opt_in = ob.get("sendblue_sms_opt_in")
    if sms_opt_in is False:
        return False
    return ob.get("sendblue_sms_engaged") is True


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
        """Same as send_message with text only (SMS/iMessage). Voice-gated."""
        return await self.send_message(to_phone, filter_text(message, context="sms"))

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

    async def send_coaching_sms(self, phone: str, message: str) -> bool:
        return bool(await self.send_sms(phone, filter_text(message, context="coaching_sms")))


sendblue_service = SendblueService()
