"""Structured telemetry helpers for chat and retrieval flows."""

from __future__ import annotations

import logging
import threading
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

_COUNTERS = Counter()
_LOCK = threading.Lock()


def _bump(name: str, delta: int = 1) -> int:
    with _LOCK:
        _COUNTERS[name] += delta
        return _COUNTERS[name]


def fast_path_snapshot(kind: str) -> dict[str, Any]:
    with _LOCK:
        total = _COUNTERS.get("chat_turns_total", 0)
    fast_total = _bump("fast_path_total")
    kind_total = _bump(f"fast_path_{kind}")
    snapshot = {
        "chat_turns_total": total,
        "fast_path_total": fast_total,
        "fast_path_kind_total": kind_total,
        "fast_path_hit_rate": round(fast_total / max(total, 1), 4),
        "fast_path_kind": kind,
    }
    logger.info("[TELEMETRY] fast_path %s", snapshot)
    return snapshot


def note_chat_turn() -> int:
    total = _bump("chat_turns_total")
    logger.debug("[TELEMETRY] chat_turn total=%d", total)
    return total


def log_context_build(*, intent: str, elapsed_ms: float, cache_hit: bool, tokens: int, sections: list[str]) -> None:
    logger.info(
        "[TELEMETRY] context_build intent=%s elapsed_ms=%.1f cache_hit=%s tokens=%d sections=%s",
        intent,
        elapsed_ms,
        cache_hit,
        tokens,
        ",".join(sections),
    )


def log_retrieval(
    *,
    maxx_id: str,
    elapsed_ms: float,
    hits: int,
    threshold: float,
    query_tokens: int,
) -> None:
    logger.info(
        "[TELEMETRY] retrieval maxx=%s elapsed_ms=%.1f hits=%d threshold=%.2f query_tokens=%d",
        maxx_id,
        elapsed_ms,
        hits,
        threshold,
        query_tokens,
    )


def log_prompt_budget(
    *,
    path: str,
    system_tokens: int,
    coaching_context_tokens: int,
    history_tokens: int,
    chunk_tokens: int,
    user_tokens: int,
    total_tokens: int,
) -> None:
    logger.info(
        "[TELEMETRY] prompt_budget path=%s system=%d coaching_context=%d history=%d chunks=%d user=%d total=%d",
        path,
        system_tokens,
        coaching_context_tokens,
        history_tokens,
        chunk_tokens,
        user_tokens,
        total_tokens,
    )


def log_agent_run(*, iterations: int, tool_calls: int, response_len: int) -> None:
    logger.info(
        "[TELEMETRY] agent_run iterations=%d tool_calls=%d response_len=%d",
        iterations,
        tool_calls,
        response_len,
    )
