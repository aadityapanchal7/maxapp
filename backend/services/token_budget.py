"""Token-aware trimming for chat context.

Most LLM cost + latency comes from prompt size. We size the prompt to a budget
(system + history + retrieved + user message + headroom) rather than hard-coded
history counts.

Uses tiktoken's cl100k_base for OpenAI models; approximates for Gemini (Gemini's
tokenizer is slightly denser but within ~10% of cl100k at English prose).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Iterable

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception as e:
        logger.warning("tiktoken unavailable (%s) — falling back to char/4 estimator", e)
        return None


def count_tokens(text: str) -> int:
    if not text:
        return 0
    enc = _encoder()
    if enc is None:
        return max(1, len(text) // 4)
    return len(enc.encode(text))


def trim_history(
    history: list[dict],
    *,
    max_tokens: int,
    keep_last: int = 4,
) -> list[dict]:
    """Drop oldest turns until the remaining content fits under max_tokens.

    Always keeps the last `keep_last` turns verbatim even if that exceeds the budget,
    so the model never loses the immediate context.
    """
    if not history:
        return []

    tail = history[-keep_last:]
    older = history[:-keep_last]

    kept: list[dict] = list(tail)
    tail_tokens = sum(count_tokens(m.get("content") or "") for m in tail)
    remaining = max_tokens - tail_tokens

    # Walk older turns from newest to oldest, keep what fits
    running = 0
    to_prepend: list[dict] = []
    for turn in reversed(older):
        t = count_tokens(turn.get("content") or "")
        if running + t > remaining:
            break
        to_prepend.append(turn)
        running += t

    return list(reversed(to_prepend)) + kept


def trim_chunks(
    chunks: list[dict],
    *,
    max_tokens: int,
) -> list[dict]:
    """Keep top chunks (order preserved) until their combined token count fits."""
    if not chunks:
        return []
    kept: list[dict] = []
    running = 0
    for c in chunks:
        t = count_tokens(c.get("content") or "")
        if running + t > max_tokens and kept:
            break
        kept.append(c)
        running += t
    return kept


def summarize_usage(*, system: str, history: Iterable[dict], chunks: Iterable[dict], user_msg: str) -> dict:
    """Return a breakdown of prompt tokens per section — for telemetry."""
    return {
        "system": count_tokens(system),
        "history": sum(count_tokens(m.get("content") or "") for m in history),
        "retrieved": sum(count_tokens(c.get("content") or "") for c in chunks),
        "user": count_tokens(user_msg),
    }
