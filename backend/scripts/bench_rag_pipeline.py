"""Benchmark the split-path RAG pipeline — retrieval, context build, and trim.

Isolates work that runs per chat turn *excluding* the LLM call itself
(which depends on network + provider latency). Reports p50 / p95 / max in
milliseconds across N iterations.

Usage:
    python -m scripts.bench_rag_pipeline
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import fast_rag_answer, lc_graph
from services.coaching_service import CoachingService, _context_requirements
from services.rag_service import reload_indexes, retrieve_chunks, _get_index, VALID_MAXX_IDS
from services.token_budget import (
    count_tokens,
    trim_context_blob,
    trim_chunks,
    trim_history,
)


# --------------------------------------------------------------------------- #
#  Fixtures — small stand-ins so we don't need a real DB / LLM                 #
# --------------------------------------------------------------------------- #

@dataclass
class _FakeUser:
    onboarding: dict = field(default_factory=lambda: {
        "timezone": "UTC",
        "skin_type": "oily",
        "primary_skin_concern": "acne",
        "goals": ["clear skin"],
        "fitmax_primary_goal": "recomp",
        "wake_time": "07:00",
        "sleep_time": "23:00",
    })
    schedule_preferences: dict = field(default_factory=dict)
    profile: dict = field(default_factory=dict)
    first_name: str = "Nisha"
    last_name: str = ""
    username: str = "nisha"
    ai_context: str = "User wants clearer skin, prefers direct coaching, avoids heavy lifts."
    coaching_tone: str = "direct"


@dataclass
class _FakeState:
    streak_days: int = 5
    missed_days: int = 0
    primary_goal: str = "clear_skin"
    weight: float | None = 70.5
    last_sleep_hours: float | None = 7.2
    last_calories: int | None = 2100
    last_mood: str | None = "good"
    injuries: list = field(default_factory=list)
    preferred_tone: str = "direct"


class _FakeScalarResult:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return list(self._value or [])


class _FakeDB:
    def __init__(self, user: _FakeUser):
        self._user = user

    async def get(self, _model, _user_uuid):
        return self._user

    async def execute(self, statement):
        sql = str(statement)
        if "FROM scans" in sql:
            return _FakeScalarResult(None)
        if "FROM user_schedules" in sql:
            return _FakeScalarResult([])
        if "app_users.onboarding" in sql:
            return _FakeScalarResult(self._user.onboarding)
        return _FakeScalarResult(None)


# --------------------------------------------------------------------------- #
#  Timing helpers                                                              #
# --------------------------------------------------------------------------- #

async def _a_time(label: str, fn: Callable[[], Awaitable], n: int) -> dict:
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        await fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return _report(label, samples)


def _time(label: str, fn: Callable[[], None], n: int) -> dict:
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return _report(label, samples)


def _report(label: str, samples: list[float]) -> dict:
    samples_sorted = sorted(samples)
    p = lambda q: samples_sorted[min(len(samples_sorted) - 1, int(q * len(samples_sorted)))]
    stats = {
        "label": label,
        "n": len(samples),
        "min_ms": round(min(samples), 3),
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(p(0.95), 3),
        "max_ms": round(max(samples), 3),
        "mean_ms": round(statistics.fmean(samples), 3),
    }
    return stats


def _print_row(stats: dict) -> None:
    print(
        f"  {stats['label']:<48} "
        f"n={stats['n']:>4}  "
        f"p50={stats['p50_ms']:>8.3f}ms  "
        f"p95={stats['p95_ms']:>8.3f}ms  "
        f"max={stats['max_ms']:>8.3f}ms  "
        f"mean={stats['mean_ms']:>8.3f}ms"
    )


# --------------------------------------------------------------------------- #
#  Benchmarks                                                                  #
# --------------------------------------------------------------------------- #

async def bench_bm25_cold_load() -> list[dict]:
    """How long does building the in-memory BM25 index for each module take?"""
    rows: list[dict] = []
    for maxx in VALID_MAXX_IDS:
        samples: list[float] = []
        for _ in range(5):
            reload_indexes()
            t0 = time.perf_counter()
            _ = _get_index(maxx)
            samples.append((time.perf_counter() - t0) * 1000)
        rows.append(_report(f"bm25_cold_load[{maxx}]", samples))
    return rows


async def bench_retrieve_warm(queries: list[str]) -> list[dict]:
    """Warm-path retrieval over a representative query mix."""
    reload_indexes()
    for maxx in VALID_MAXX_IDS:
        _get_index(maxx)

    rows: list[dict] = []
    for maxx in ("skinmax", "fitmax", "bonemax"):
        async def _once(m=maxx, q=queries):
            await retrieve_chunks(None, m, q[0], k=4, min_similarity=0.35)

        rows.append(await _a_time(f"retrieve_warm[{maxx}]", _once, 200))

        async def _mixed(m=maxx, q=queries):
            # Cycle through the query mix
            await retrieve_chunks(None, m, q[time.perf_counter_ns() % len(q)], k=4, min_similarity=0.35)

        rows.append(await _a_time(f"retrieve_warm_mixed[{maxx}]", _mixed, 200))
    return rows


async def bench_gather_evidence() -> list[dict]:
    """Full fan-out retrieval (multi-maxx) — excludes the LLM call."""
    reload_indexes()
    for maxx in VALID_MAXX_IDS:
        _get_index(maxx)

    rows: list[dict] = []

    async def _single_hint():
        await fast_rag_answer.gather_rag_evidence(
            message="what should i do for acne at night",
            maxx_hints=["skinmax"],
        )

    async def _multi_hint():
        await fast_rag_answer.gather_rag_evidence(
            message="jaw structure and mewing basics",
            maxx_hints=["bonemax", "skinmax"],
        )

    rows.append(await _a_time("gather_evidence[1 hint]", _single_hint, 150))
    rows.append(await _a_time("gather_evidence[2 hints]", _multi_hint, 150))
    return rows


async def bench_context_build() -> list[dict]:
    """build_full_context per intent — times DB + string assembly (no LLM)."""
    service = CoachingService()

    async def _fake_state(*_args, **_kwargs):
        return _FakeState()

    service.get_or_create_state = _fake_state  # type: ignore[assignment]
    fake_db = _FakeDB(_FakeUser())

    rows: list[dict] = []
    for intent in ("GREETING", "KNOWLEDGE", "CHECK_IN", "SCHEDULE_CHANGE", "OTHER"):
        async def _once(i=intent):
            # Force cache-miss each iteration by using a different user id.
            await service.build_full_context(
                f"00000000-0000-0000-0000-{int(time.perf_counter_ns() % 10**12):012d}",
                fake_db,
                None,
                intent=i,
            )

        rows.append(await _a_time(f"build_full_context[{intent}]", _once, 100))
    return rows


def bench_token_budget() -> list[dict]:
    """Hard-cap trimming for context, history, and chunks."""
    rows: list[dict] = []

    big_blob = ("this is a coaching context bit — " * 400) + "TAIL"
    rows.append(_time("trim_context_blob[~3k tokens]", lambda: trim_context_blob(big_blob, max_tokens=1800), 500))
    rows.append(_time("trim_context_blob[hard 300]", lambda: trim_context_blob(big_blob, max_tokens=300), 500))

    history = [{"role": "user", "content": "short msg " * 10} for _ in range(40)]
    rows.append(_time("trim_history[40 turns -> budget 1000]", lambda: trim_history(history, max_tokens=1000, keep_last=4), 500))

    chunks = [{"content": ("evidence sentence " * 60)} for _ in range(12)]
    rows.append(_time("trim_chunks[12 -> budget 800]", lambda: trim_chunks(chunks, max_tokens=800), 500))

    return rows


async def bench_graph_knowledge_path() -> list[dict]:
    """Full LangGraph path for a KNOWLEDGE turn, with LLM stubbed out."""
    lc_graph.rebuild_graph()

    fake_chunks = [
        {
            "id": "routines:0:deadbeef",
            "content": "at night: gentle cleanser, then adapalene, then moisturizer.",
            "doc_title": "routines",
            "chunk_index": 0,
            "similarity": 0.9,
            "metadata": {
                "source": "rag_docs/skinmax/routines.md",
                "section": "PM routine",
            },
        }
    ]

    async def _fake_retrieve(_db, _maxx, _query, **_kwargs):
        return list(fake_chunks)

    async def _fake_answer(*, message: str, retrieved: list[dict]):
        return "use the PM routine. [source: rag_docs/skinmax/routines.md > PM routine]"

    import services.rag_service as rag_service
    rag_service.retrieve_chunks = _fake_retrieve  # type: ignore[assignment]
    lc_graph.answer_from_chunks = _fake_answer  # type: ignore[assignment]

    async def _once():
        await lc_graph.run_graph_chat(
            message="what should i do for acne at night",
            history=[],
            user_context={"coaching_context": "", "active_schedule": None, "onboarding": {}},
            user_id="00000000-0000-0000-0000-000000000000",
            make_tools=lambda: [],
            maxx_id="skinmax",
            active_maxx="skinmax",
            channel="app",
        )

    return [await _a_time("graph_knowledge_path[stubbed]", _once, 100)]


def bench_context_requirements_decision() -> list[dict]:
    rows: list[dict] = []
    for intent in ("GREETING", "KNOWLEDGE", "CHECK_IN", "OTHER", "SCHEDULE_CHANGE"):
        rows.append(_time(f"context_requirements[{intent}]", lambda i=intent: _context_requirements(i), 2000))
    return rows


# --------------------------------------------------------------------------- #
#  Entry                                                                       #
# --------------------------------------------------------------------------- #

async def main() -> None:
    queries = [
        "what should i do for acne at night",
        "best PM routine",
        "how to cut for summer",
        "mewing tongue position",
        "posture fixes for sitting all day",
        "minoxidil application frequency",
        "protein intake for lean bulk",
    ]

    print("\n=== RAG + CHAT PIPELINE BENCHMARK ===\n")

    print("[1/6] BM25 cold-load per module")
    for row in await bench_bm25_cold_load():
        _print_row(row)

    print("\n[2/6] Warm retrieval (in-memory BM25)")
    for row in await bench_retrieve_warm(queries):
        _print_row(row)

    print("\n[3/6] gather_rag_evidence (fast-path retrieval, no LLM)")
    for row in await bench_gather_evidence():
        _print_row(row)

    print("\n[4/6] build_full_context per intent (fake DB, no LLM)")
    for row in await bench_context_build():
        _print_row(row)

    print("\n[5/6] Token budget trimming")
    for row in bench_token_budget():
        _print_row(row)

    print("\n[6/6] LangGraph KNOWLEDGE path, stubbed LLM")
    for row in await bench_graph_knowledge_path():
        _print_row(row)

    print("\n[side] context_requirements dispatch cost")
    for row in bench_context_requirements_decision():
        _print_row(row)

    print()


if __name__ == "__main__":
    asyncio.run(main())
