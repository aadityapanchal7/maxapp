"""
Structured LLM classifier: which Maxx module (if any) the current chat turn is about.

Used by api.chat.process_chat_message instead of keyword heuristics on the user message.
init_context is passed only as a hint; the model returns the final maxx_id or null.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from services.lc_providers import get_primary_llm

logger = logging.getLogger(__name__)

_KNOWN_MAXX = frozenset({"skinmax", "hairmax", "heightmax", "fitmax", "bonemax"})


class MaxxChatIntent(BaseModel):
    """Structured output for maxx routing."""

    maxx_id: Optional[
        Literal["skinmax", "hairmax", "heightmax", "fitmax", "bonemax"]
    ] = Field(
        default=None,
        description="Module this turn is about, or null if general / unrelated chat.",
    )


_SYSTEM_PROMPT = """You classify which single Maxx coaching module (if any) this chat turn is about.

Known modules: skinmax, hairmax, heightmax, fitmax, bonemax.

Rules:
- The client may send init_context as a hint for which screen/module the user opened. Treat it as context, not a hard override: if the user message clearly focuses a different module, return that module instead.
- If the user is only greeting, small talk, or asking something not tied to starting or continuing a specific module, return maxx_id null.
- If they are clearly starting, continuing, or asking setup/questions for one module, return that maxx_id.
- heightmax_app_kickoff is true only for the app's auto kickoff line when opening HeightMax schedule. When true, return heightmax unless the user message clearly belongs to another module.
- channel is "sms" or "app"; use it only as tone context, not to change the taxonomy.

Reply with JSON matching the schema (maxx_id only)."""


async def infer_maxx_chat_intent(
    *,
    message_text: str,
    init_context: Optional[str],
    channel: str,
    active_maxx_hint: Optional[str],
    heightmax_app_kickoff: bool = False,
) -> Optional[str]:
    """
    Return a normalized maxx id or None. On LLM/parse errors, returns None.
    """
    text = (message_text or "").strip()
    if not text:
        return None

    hint = (init_context or "").strip() or "(none)"
    active = (active_maxx_hint or "").strip() or "(none)"
    kick = "yes" if heightmax_app_kickoff else "no"

    human = (
        f"init_context hint: {hint}\n"
        f"active_schedule maxx_id hint: {active}\n"
        f"heightmax_app_kickoff: {kick}\n"
        f"channel: {channel}\n\n"
        f"user_message:\n{text}"
    )

    try:
        llm = get_primary_llm(max_tokens=128).bind(temperature=0.2)
        structured = llm.with_structured_output(MaxxChatIntent)
        out: MaxxChatIntent = await structured.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=human),
            ]
        )
        mid = out.maxx_id
        if mid and str(mid).lower() in _KNOWN_MAXX:
            return str(mid).lower()
        return None
    except Exception as e:
        logger.warning("infer_maxx_chat_intent failed, returning null: %s", e)
        return None
