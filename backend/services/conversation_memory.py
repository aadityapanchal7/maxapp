"""Two-layer conversational memory builder.

Single source of truth for "what does the model see about this user and
this conversation." Replaces ad-hoc prompt-stuffing in chat handlers and
gives the fast_rag path the same recent-turn awareness the agent path
already has.

Two layers:
  1. **Recent turns** — last N user/assistant exchanges, character-budgeted,
     formatted as a compact transcript. This is what fixes "i don't eat
     meat" → "plan me lunch" continuity in the fast_rag path.
  2. **User profile** — identity-level facts that don't change turn-to-turn:
     stored user_facts (vegetarian, allergies, eczema), onboarding values
     (gender, age, response-length preference, climate), durable schedule
     prefs (wake_time, equipment). Cheap to recompute, but stable per user.

Both layers ship as plain strings so any prompt-builder can drop them in
without coupling to the dataclass.

Budgets: ~600 chars for recent turns (~150 tokens) and ~400 chars for
profile (~100 tokens). Total memory footprint < 1KB / ~250 tokens — small
enough to include on every turn even at the cheapest tier.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Data class                                                                 #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MemoryContext:
    """Bundle of memory blocks for a single turn.

    Each field is a ready-to-inject string (or "" if there's nothing to
    show). Callers compose them into prompts however they like; nothing
    in this module assumes a particular prompt structure.
    """
    recent_turns: str       # transcript of last N exchanges (user_message excluded)
    user_profile: str       # identity / facts / preferences block
    char_count: int         # total chars of the two blocks combined

    @property
    def is_empty(self) -> bool:
        return not self.recent_turns and not self.user_profile


# --------------------------------------------------------------------------- #
#  Recent-turns formatter                                                     #
# --------------------------------------------------------------------------- #

def format_recent_turns(
    history: Optional[list[dict[str, Any]]],
    *,
    max_turns: int = 6,
    char_budget: int = 600,
    per_message_chars: int = 220,
) -> str:
    """Render the last few user/assistant exchanges as a compact transcript.

    Args:
      history:           list of {"role", "content"} dicts in chronological
                         order. The CURRENT user turn should NOT be in
                         this list — pass `history[:-1]` if it is.
      max_turns:         take at most the last N messages.
      char_budget:       hard upper bound on total output length.
      per_message_chars: truncate any single message past this length.

    Returns "" when history is empty.

    Format:
        [user] short message
        [bot]  short reply
        [user] another message
        ...
    """
    if not history:
        return ""
    # Take the trailing slice and trim each message.
    tail = list(history)[-max_turns:]
    lines: list[str] = []
    running = 0
    for h in tail:
        role = (h.get("role") or "").strip().lower()
        if role not in ("user", "assistant", "bot"):
            continue
        tag = "[user]" if role == "user" else "[bot] "
        content = (h.get("content") or "").strip().replace("\n", " ")
        if len(content) > per_message_chars:
            content = content[: per_message_chars - 1].rstrip() + "…"
        line = f"{tag} {content}"
        # Apply the budget — if this line would overflow, stop adding more.
        # We prefer recent over old, so stop FORWARD walk; the early-msg
        # truncation will lose oldest messages first.
        if running + len(line) + 1 > char_budget:
            break
        lines.append(line)
        running += len(line) + 1
    if not lines:
        return ""
    return (
        "## RECENT CONVERSATION (most recent last — use for continuity, "
        "do NOT contradict)\n" + "\n".join(lines)
    )


# --------------------------------------------------------------------------- #
#  User-profile formatter                                                     #
# --------------------------------------------------------------------------- #

# Onboarding keys we surface in the profile block. Skipping noisy ones
# (e.g. timezone offsets, raw enum integers) keeps the prompt readable.
_ONBOARDING_KEYS_OF_INTEREST = (
    ("gender", "gender"),
    ("age", "age"),
    ("dob", "date of birth"),
    ("location", "location"),
    ("climate", "climate"),
    ("wake_time", "wakes around"),
    ("sleep_time", "sleeps around"),
    ("training_status", "training"),
    ("response_length", "preferred response length"),
    ("goal", "goal"),
    ("primary_goal", "primary goal"),
)


def format_user_profile(
    *,
    user_facts: Optional[dict[str, Any]] = None,
    onboarding: Optional[dict[str, Any]] = None,
    persistent_ctx: Optional[dict[str, Any]] = None,
    char_budget: int = 400,
) -> str:
    """Render a stable, identity-level profile block.

    Sources merged (most-trusted first):
      - user_facts:     stored constraints (extracted from chat over time)
      - onboarding:     answers from signup flow + schedule_preferences
      - persistent_ctx: long-term user_schedule_context (excluding user_facts
                        which is already shown above)

    Returns "" when nothing useful is available.
    """
    sections: list[str] = []

    # --- Facts (most important — already filtered for relevance) ---------
    if user_facts:
        try:
            from services.user_facts_service import format_facts_for_prompt
            facts_str = format_facts_for_prompt(user_facts)
            if facts_str:
                # `format_facts_for_prompt` already emits a header — strip
                # it here so we control header formatting consistently.
                body = facts_str.split("\n", 1)[1] if "\n" in facts_str else facts_str
                sections.append("Known facts:\n" + body)
        except Exception:
            pass

    # --- Onboarding identity ---------------------------------------------
    onboarding = onboarding or {}
    onboarding_lines: list[str] = []
    for key, label in _ONBOARDING_KEYS_OF_INTEREST:
        v = onboarding.get(key)
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v if x)
            if not v:
                continue
        onboarding_lines.append(f"- {label}: {v}")
    if onboarding_lines:
        sections.append("Onboarding:\n" + "\n".join(onboarding_lines))

    # --- Other persistent context (light touch) --------------------------
    if persistent_ctx:
        # Skip user_facts (shown above) and noisy internal keys.
        skip = {"user_facts", "_pending_intent", "_stated_at"}
        small_lines: list[str] = []
        for k, v in (persistent_ctx or {}).items():
            if k in skip or not v:
                continue
            if isinstance(v, dict):
                continue  # nested objects rarely render well in 1 line
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v[:5])
                if not v:
                    continue
            s = str(v)
            if len(s) > 80:
                s = s[:79] + "…"
            small_lines.append(f"- {k}: {s}")
            if len(small_lines) >= 5:
                break
        if small_lines:
            sections.append("Preferences:\n" + "\n".join(small_lines))

    if not sections:
        return ""

    body = "\n\n".join(sections)
    if len(body) > char_budget:
        # Hard truncate at the budget boundary, ending on a newline if we
        # can find one nearby.
        cut = body.rfind("\n", 0, char_budget)
        if cut < 0 or cut < char_budget - 80:
            cut = char_budget
        body = body[:cut].rstrip() + "\n…"
    return "## USER PROFILE (stable identity / preferences)\n" + body


# --------------------------------------------------------------------------- #
#  Top-level builder                                                          #
# --------------------------------------------------------------------------- #

def build_memory_context(
    *,
    history: Optional[list[dict[str, Any]]] = None,
    user_facts: Optional[dict[str, Any]] = None,
    onboarding: Optional[dict[str, Any]] = None,
    persistent_ctx: Optional[dict[str, Any]] = None,
    exclude_current_user_message: bool = True,
    max_recent_turns: int = 6,
) -> MemoryContext:
    """Build a unified MemoryContext for one conversation turn.

    `history` should be the chronologically-ordered list of prior messages.
    If it INCLUDES the current user message (the chat handler often
    persists it before LLM call), set `exclude_current_user_message=True`
    (default) to drop the trailing user row.

    The returned object is safe to share across path implementations —
    fast_rag and the agent path consume the same strings.
    """
    h = list(history or [])
    if exclude_current_user_message and h and (h[-1].get("role") == "user"):
        h = h[:-1]

    recent = format_recent_turns(h, max_turns=max_recent_turns)
    profile = format_user_profile(
        user_facts=user_facts,
        onboarding=onboarding,
        persistent_ctx=persistent_ctx,
    )
    total = len(recent) + len(profile)
    return MemoryContext(
        recent_turns=recent,
        user_profile=profile,
        char_count=total,
    )
