"""Heuristic intent classifier — keyword-first, zero LLM calls.

Used by the LangGraph chat pipeline to decide:
  * whether to retrieve RAG context (only KNOWLEDGE queries)
  * whether to fan out retrieval across multiple maxx namespaces
  * whether to short-circuit check-ins to the log_check_in tool directly

Design: return the classification as a dict rather than an enum so additional
signals (multi-maxx fan-out, injection flags, etc.) travel alongside the intent.

Contract:
    classify_turn(message) -> {
        "intent": "KNOWLEDGE" | "CHECK_IN" | "SCHEDULE_CHANGE" |
                  "ONBOARDING" | "GREETING" | "OTHER",
        "maxx_hints": list[str],   # e.g. ["skinmax", "bonemax"]
        "skip_rag": bool,
        "confidence": "high" | "medium" | "low",
    }
"""

from __future__ import annotations

import re
from typing import TypedDict


class IntentResult(TypedDict):
    intent: str
    maxx_hints: list[str]
    skip_rag: bool
    confidence: str


# Keyword lexicons. Ordered list so we can preserve match order for maxx_hints.
_MAXX_KEYWORDS = [
    ("skinmax", {"skin", "acne", "pimple", "pore", "blackhead", "wrinkle", "sunscreen", "spf",
                 "retinol", "retinoid", "moisturizer", "sebum", "glycolic", "salicylic",
                 "debloat", "debloating", "bloat", "bloated", "puffy", "puffy face",
                 "dark spot", "hyperpigment", "ice roller", "glowmax", "glow up",
                 "skinmaxxing"}),
    ("hairmax", {"hair", "bald", "balding", "receding", "thinning", "minoxidil", "finasteride",
                 "dermaroll", "dermarolling", "shampoo", "scalp", "dht", "alopecia",
                 "norwood", "nw1", "nw2", "nw3", "hair tape", "hair gain", "hairmaxxing",
                 "hairline"}),
    ("bonemax", {"jaw", "mewing", "chin", "mastic", "bite", "bite force", "tmj",
                 "cheekbone", "zygomatic", "skull", "jawline", "palate", "tongue posture",
                 "bonesmash", "bonesmashing", "bone smash", "bone smashing",
                 "bonemashing", "gonion", "gonial", "maxilla", "mandible",
                 "looksmax", "looksmaxxing", "looksmaxx", "psl", "facemax",
                 "facemaxxing", "bonemaxxing"}),
    ("heightmax", {"height", "taller", "posture", "spine", "growth plate", "hgh",
                   "slouch", "kyphosis", "lordosis", "decompression", "hanging",
                   "heightmaxxing", "grow taller", "spinal"}),
    ("fitmax", {"workout", "lift", "muscle", "protein", "calorie", "deficit", "cut", "bulk",
                "cardio", "squat", "deadlift", "bench", "cutting", "macro", "macros",
                "fitmaxxing", "leanmax", "gym", "hypertrophy", "recomp", "tdee"}),
]

_KNOWLEDGE_MARKERS = (
    "what", "why", "how", "when", "which", "who",
    "?", "explain", "tell me", "difference", "benefit",
    "does ", "should i", "can i", "is it", "is a ", "are ", "work?", "works?",
    "give me", "list of", "recommend", "routine", "what do i", "what should",
    "tips", "advice", "best ", "help with", "detail",
)

_CHECK_IN_MARKERS = (
    "did my", "finished my", "done with", "knocked out", "completed",
    "slept", "sleep was", "ate ", "calories today", "missed",
    "worked out", "skipped", "feeling ", "mood is", "injury", "hurt my", "pulled a",
)

_SCHEDULE_CHANGE_MARKERS = (
    "reschedule", "move my", "shift my", "change my wake", "change my sleep",
    "waking at", "sleeping at", "wake up at", "bedtime", "earlier", "later",
    "add to schedule", "remove from schedule", "push back", "bring forward",
    "i'm free at", "not free at",
)

_ONBOARDING_MARKERS = (
    "start ", "begin ", "set up", "new schedule", "onboard",
    "i want to try", "how do i begin", "get me started",
)

_GREETING_PATTERNS = (
    r"^\s*(hi|hey|hello|yo|sup|wassup|morning|good morning|gm|gn|good night)\s*[!?.]*\s*$",
    r"^\s*(thanks|thank you|ty|thx|ok|okay|cool|got it|word|bet)\s*[!?.]*\s*$",
)

_INJECTION_MARKERS = (
    "ignore previous", "ignore the above", "disregard previous", "forget everything",
    "pretend you are", "act as if you are", "system prompt", "jailbreak",
    "dan mode", "developer mode", "reveal your instructions", "print your system prompt",
)


def _maxx_hints_for(text: str) -> list[str]:
    text_l = f" {text.lower()} "
    hits: list[str] = []
    for maxx, kws in _MAXX_KEYWORDS:
        if any(kw in text_l for kw in kws):
            hits.append(maxx)
    return hits


def is_injection_attempt(message: str) -> bool:
    m = (message or "").lower()
    return any(marker in m for marker in _INJECTION_MARKERS)


def classify_turn(message: str, *, active_maxx: str | None = None) -> IntentResult:
    """Classify a single user turn into an intent bucket.

    active_maxx flows in when the user has a schedule active — we use it as a
    tiebreaker if no keywords hint at a module.
    """
    text = (message or "").strip()
    if not text:
        return IntentResult(intent="OTHER", maxx_hints=[], skip_rag=True, confidence="high")

    m = text.lower()

    # Greetings / small talk — short inputs, no retrieval
    for pat in _GREETING_PATTERNS:
        if re.match(pat, m):
            return IntentResult(intent="GREETING", maxx_hints=[], skip_rag=True, confidence="high")

    # Single-word or numeric replies (check-in acks, ratings)
    if len(m.split()) <= 2:
        try:
            float(m.replace(" ", ""))
            return IntentResult(intent="CHECK_IN", maxx_hints=[], skip_rag=True, confidence="high")
        except ValueError:
            pass
        if m.strip(".,!?") in {"yes", "no", "yep", "nope", "done", "finished", "skipped", "missed"}:
            return IntentResult(intent="CHECK_IN", maxx_hints=[], skip_rag=True, confidence="high")

    hints = _maxx_hints_for(m)
    if not hints and active_maxx:
        hints = [active_maxx]

    # Schedule-change phrasing (checked before knowledge because "change my wake time"
    # technically contains "change" which is neutral)
    if any(marker in m for marker in _SCHEDULE_CHANGE_MARKERS):
        return IntentResult(
            intent="SCHEDULE_CHANGE",
            maxx_hints=hints,
            skip_rag=True,
            confidence="high",
        )

    # Onboarding intent
    if any(marker in m for marker in _ONBOARDING_MARKERS):
        return IntentResult(
            intent="ONBOARDING",
            maxx_hints=hints,
            skip_rag=False,   # RAG can still inform the onboarding answer
            confidence="medium",
        )

    # Check-in phrasing
    if any(marker in m for marker in _CHECK_IN_MARKERS):
        return IntentResult(
            intent="CHECK_IN",
            maxx_hints=hints,
            skip_rag=True,
            confidence="medium",
        )

    # Knowledge questions — default when the user wants info
    if any(marker in m for marker in _KNOWLEDGE_MARKERS) or len(text) > 40:
        conf = "high" if hints else "medium"
        return IntentResult(
            intent="KNOWLEDGE",
            maxx_hints=hints,
            skip_rag=False,
            confidence=conf,
        )

    # Topic-named queries without an explicit question marker (e.g.
    # "bonesmashing routine", "debloating fast", "looksmaxxing protocol").
    # If a module lexicon matched, treat as KNOWLEDGE so RAG fires.
    if hints:
        return IntentResult(
            intent="KNOWLEDGE",
            maxx_hints=hints,
            skip_rag=False,
            confidence="medium",
        )

    # Unknown — route to agent without RAG
    return IntentResult(intent="OTHER", maxx_hints=hints, skip_rag=True, confidence="low")
