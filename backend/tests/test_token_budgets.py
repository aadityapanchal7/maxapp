"""Hard-cap enforcement for coaching context and system prompt tokens."""

from __future__ import annotations

import pytest

from services.token_budget import (
    count_tokens,
    trim_chunks,
    trim_context_blob,
    trim_history,
    trim_text_block,
)


def _blob(char: str, repeat: int) -> str:
    return (char * 12 + " ") * repeat


def test_trim_context_blob_respects_hard_cap():
    big = _blob("x", 5000)
    assert count_tokens(big) > 200
    clamped = trim_context_blob(big, max_tokens=200)
    assert count_tokens(clamped) <= 200


def test_trim_context_blob_preserves_head_and_tail():
    head = "HEADER FACTS that must survive — user=nisha goal=clear_skin tolerances=sensitive"
    tail = "TAIL TRAILING SENTINEL MUST REMAIN"
    middle = _blob("y", 4000)
    combined = f"{head}\n\n{middle}\n\n{tail}"
    # Budget large enough that the 1400-char head + 800-char tail window fits,
    # but smaller than the full 48k-char blob — forces the trim path.
    clamped = trim_context_blob(combined, max_tokens=800)
    assert "HEADER FACTS" in clamped
    assert "TAIL TRAILING SENTINEL" in clamped
    assert "[... trimmed for budget ...]" in clamped
    assert count_tokens(clamped) <= 800


def test_trim_text_block_hits_budget_for_short_input():
    raw = "already short enough"
    assert trim_text_block(raw, max_tokens=100) == raw


def test_trim_history_keeps_recent_turns_even_past_budget():
    history = [
        {"role": "user", "content": "old one " * 400},
        {"role": "assistant", "content": "older response " * 400},
        {"role": "user", "content": "recent question"},
        {"role": "assistant", "content": "recent answer"},
    ]
    trimmed = trim_history(history, max_tokens=20, keep_last=2)
    assert trimmed[-2]["content"] == "recent question"
    assert trimmed[-1]["content"] == "recent answer"


def test_trim_chunks_stops_when_budget_exhausted():
    chunks = [
        {"content": "chunk-alpha " * 100},
        {"content": "chunk-beta " * 100},
        {"content": "chunk-gamma " * 100},
    ]
    kept = trim_chunks(chunks, max_tokens=120)
    assert 1 <= len(kept) < len(chunks)
    assert kept[0] is chunks[0]


@pytest.mark.asyncio
async def test_agent_system_prompt_is_bounded(monkeypatch):
    from services import lc_agent

    async def _fake_resolve(*_args, **_kwargs):
        return "BASE SYSTEM PROMPT"

    # asyncio.to_thread(resolve_prompt, ...) → short-circuit
    monkeypatch.setattr(
        lc_agent, "resolve_prompt", lambda *_args, **_kwargs: "BASE SYSTEM PROMPT"
    )

    # Oversize coaching_context — must be clamped before the final budget check.
    huge_context = "COACHING CONTEXT START " + ("blabber " * 40000) + " COACHING CONTEXT END"

    prompt = await lc_agent.build_agent_system_prompt(
        user_context={"coaching_context": huge_context},
        delivery_channel="app",
    )

    tokens = count_tokens(prompt)
    # Must stay within the hard system-prompt budget (default 3200).
    assert tokens <= 3300, f"system prompt exceeded budget: {tokens}"
    assert "COACHING CONTEXT START" in prompt  # head preserved
