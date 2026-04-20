"""Ensure structured telemetry is emitted at each split-path boundary."""

from __future__ import annotations

import logging

import pytest

from services import chat_telemetry


def test_fast_path_snapshot_emits_log(caplog):
    caplog.set_level(logging.INFO, logger="services.chat_telemetry")
    chat_telemetry.note_chat_turn()
    snap = chat_telemetry.fast_path_snapshot("knowledge")
    assert snap["fast_path_kind"] == "knowledge"
    assert snap["chat_turns_total"] >= 1
    messages = [r.getMessage() for r in caplog.records]
    assert any("fast_path" in m for m in messages)


def test_log_context_build_shape(caplog):
    caplog.set_level(logging.INFO, logger="services.chat_telemetry")
    chat_telemetry.log_context_build(
        intent="GREETING",
        elapsed_ms=12.4,
        cache_hit=False,
        tokens=640,
        sections=["account", "memory_slots"],
    )
    messages = [r.getMessage() for r in caplog.records]
    joined = "\n".join(messages)
    assert "context_build" in joined
    assert "intent=GREETING" in joined
    assert "account,memory_slots" in joined


def test_log_retrieval_shape(caplog):
    caplog.set_level(logging.INFO, logger="services.chat_telemetry")
    chat_telemetry.log_retrieval(
        maxx_id="skinmax",
        elapsed_ms=3.2,
        hits=4,
        threshold=0.35,
        query_tokens=7,
    )
    messages = [r.getMessage() for r in caplog.records]
    joined = "\n".join(messages)
    assert "retrieval" in joined
    assert "maxx=skinmax" in joined
    assert "threshold=0.35" in joined


def test_log_prompt_budget_separates_sections(caplog):
    caplog.set_level(logging.INFO, logger="services.chat_telemetry")
    chat_telemetry.log_prompt_budget(
        path="agent",
        system_tokens=800,
        coaching_context_tokens=1200,
        history_tokens=400,
        chunk_tokens=150,
        user_tokens=30,
        total_tokens=2580,
    )
    messages = [r.getMessage() for r in caplog.records]
    joined = "\n".join(messages)
    assert "prompt_budget" in joined
    assert "path=agent" in joined
    assert "coaching_context=1200" in joined
    assert "chunks=150" in joined


def test_log_agent_run_emits(caplog):
    caplog.set_level(logging.INFO, logger="services.chat_telemetry")
    chat_telemetry.log_agent_run(iterations=2, tool_calls=1, response_len=420)
    messages = [r.getMessage() for r in caplog.records]
    joined = "\n".join(messages)
    assert "agent_run" in joined
    assert "iterations=2" in joined
    assert "tool_calls=1" in joined
