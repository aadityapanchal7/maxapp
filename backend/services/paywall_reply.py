"""Paywall reply generator for unsubscribed inbound SMS/iMessage.

Unsubscribed users hitting the Sendblue webhook previously got a single
hardcoded string on every message, which looped if they replied with slang
or nonsense. This module generates a short, dynamic reply that:

  1. Acknowledges what they actually said (no copy-paste).
  2. Holds the subscription wall (no coaching, no tools).
  3. Varies across consecutive turns (chat history is fed to the model).

A static rotation of three variants is the fallback when the LLM call fails
or times out so inbound SMS is never silent.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Optional

from config import settings
from services.lc_providers import get_chat_llm_with_fallback

logger = logging.getLogger(__name__)


_PAYWALL_SYSTEM_PROMPT = """You are Max, but in PAYWALL MODE. The user is unsubscribed and cannot be coached.

RULES (no exceptions):
- Acknowledge what they just said in 3-6 words ("yeah fair", "heard, but —", "bet, still —", "nah i got you but —").
- Then hold the line: they need to subscribe in the Max app to continue. Short, direct.
- NO coaching. NO advice. NO product recs. NO tool calls (you have none).
- NEVER repeat a line you used in recent chat history — vary the acknowledgment.
- Under 18 words total, one sentence. lowercase. Max's voice (direct, a bit dry, no filler).
- NEVER promise specific content "after" they sub beyond "we can actually go back and forth then".
- If their message is nonsense, slang, or frustration, still acknowledge it with dry humor — don't ignore it and don't lecture.

Examples of good replies (not to copy verbatim):
- "yeah heard — still gotta sub in the app before i can actually coach."
- "bet, but wall's up till you sub. 30 seconds in max."
- "nah i feel you, but nothing i can do here unpaid — app, sub, then we text."
"""


_FALLBACK_VARIANTS: tuple[str, ...] = (
    "heard you — still need an active sub to coach from here. open max and sub, then we can actually go back and forth.",
    "bet, but wall's up till you sub. 30 seconds in the max app and we're good.",
    "not ignoring you — can't coach over sms till you're subbed. sub in the app, we're set.",
)


def _fallback_reply(user_id: str, recent_history: list[dict]) -> str:
    """Rotate deterministically per user based on how many assistant lines we've already sent."""
    assistant_count = sum(1 for m in recent_history if (m.get("role") or "").lower() == "assistant")
    if assistant_count == 0:
        seed = hashlib.md5(user_id.encode("utf-8")).hexdigest()
        idx = int(seed[:2], 16) % len(_FALLBACK_VARIANTS)
    else:
        idx = assistant_count % len(_FALLBACK_VARIANTS)
    return _FALLBACK_VARIANTS[idx]


async def generate_paywall_reply(
    *,
    user_id: str,
    inbound_message: str,
    recent_history: Optional[list[dict]] = None,
) -> str:
    """Return a dynamic paywall-enforcing reply for the given inbound message.

    `recent_history` is a list of {"role", "content"} dicts from the most
    recent turns in either direction (oldest → newest, max ~6 entries).
    Falls back to a rotating static variant if the LLM call fails.
    """
    history = (recent_history or [])[-6:]
    user_id_safe = (user_id or "anon")[:36]

    body = (inbound_message or "").strip()
    if not body:
        return _fallback_reply(user_id_safe, history)

    try:
        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

        llm = get_chat_llm_with_fallback(max_tokens=60, temperature=0.6)
        messages: list = [SystemMessage(content=_PAYWALL_SYSTEM_PROMPT)]
        for turn in history:
            role = (turn.get("role") or "").lower()
            content = (turn.get("content") or "").strip()
            if not content:
                continue
            if role == "assistant":
                messages.append(AIMessage(content=content))
            else:
                messages.append(HumanMessage(content=content))
        messages.append(HumanMessage(content=body))

        timeout_s = float(getattr(settings, "llm_timeout_seconds", 20) or 20)
        resp = await asyncio.wait_for(llm.ainvoke(messages), timeout=timeout_s)
        text = getattr(resp, "content", resp)
        if isinstance(text, list):
            text = "\n".join(str(x) for x in text)
        out = str(text or "").strip()
        if out:
            # Belt-and-suspenders: hard-cap length in case the model ignored the prompt.
            if len(out) > 180:
                out = out[:180].rstrip()
            return out
    except asyncio.TimeoutError:
        logger.warning("[paywall_reply] LLM timeout for user=%s", user_id_safe[:8])
    except Exception as e:
        logger.warning("[paywall_reply] LLM error for user=%s: %s", user_id_safe[:8], e)

    return _fallback_reply(user_id_safe, history)
