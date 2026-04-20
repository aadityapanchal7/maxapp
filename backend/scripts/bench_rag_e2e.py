"""End-to-end RAG pipeline benchmark, including real LLM calls.

Measures wall-clock latency a real user experiences — retrieval, graph routing,
LLM inference, and answer synthesis.

Three paths are exercised:
  1. fast_rag_answer.answer_from_rag(...)  — direct KNOWLEDGE bypass
  2. lc_graph.run_graph_chat(...)         — full LangGraph KNOWLEDGE path
  3. lc_graph.run_graph_chat(...)         — OTHER intent path (agent, no tools)

Requires:
  - rag_docs/ populated (skinmax has real content)
  - GEMINI_API_KEY or OPENAI_API_KEY in .env

Usage:
  python -m scripts.bench_rag_e2e                  # default: 6 iters each
  ITERS=10 python -m scripts.bench_rag_e2e         # bump iteration count
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from services import fast_rag_answer, lc_graph
from services.intent_classifier import classify_turn
from services.rag_service import reload_indexes, _get_index, VALID_MAXX_IDS


ITERS = int(os.environ.get("ITERS", 6))
# Gemini free tier is 5 req/min; pace requests by default so we stay under it.
SLEEP_BETWEEN = float(os.environ.get("BENCH_SLEEP_SEC", 13.0))


KNOWLEDGE_QUERIES = [
    ("skinmax", "what should i do for acne at night"),
    ("skinmax", "what is the best morning routine for oily skin?"),
    ("fitmax", "what is the best split for hypertrophy?"),
    ("fitmax", "how should i set macros for cutting at 180 lbs?"),
    ("skinmax", "how often should i use adapalene?"),
    ("fitmax", "what is the minimum equipment for leg day?"),
]

# Intent that should go through the agent path rather than the knowledge node.
OTHER_QUERIES = [
    "i want to start a new skinmax schedule",
    "change my schedule to wake at 6",
    "i missed my workout today",
]


def _report(label: str, samples: list[float]) -> None:
    if not samples:
        print(f"  {label:<46} n=0  (no samples)")
        return
    samples_sorted = sorted(samples)
    p = lambda q: samples_sorted[min(len(samples_sorted) - 1, int(q * len(samples_sorted)))]
    print(
        f"  {label:<46} "
        f"n={len(samples):>3}  "
        f"min={min(samples):>7.0f}ms  "
        f"p50={statistics.median(samples):>7.0f}ms  "
        f"p95={p(0.95):>7.0f}ms  "
        f"max={max(samples):>7.0f}ms  "
        f"mean={statistics.fmean(samples):>7.0f}ms"
    )


async def warm_indexes() -> None:
    reload_indexes()
    for maxx in VALID_MAXX_IDS:
        _get_index(maxx)


async def bench_fast_rag() -> None:
    samples: list[float] = []  # only real LLM successes
    error_samples: list[float] = []
    successes = 0
    for i in range(ITERS):
        maxx, q = KNOWLEDGE_QUERIES[i % len(KNOWLEDGE_QUERIES)]
        t0 = time.perf_counter()
        try:
            text, chunks = await fast_rag_answer.answer_from_rag(
                message=q,
                maxx_hints=[maxx],
                active_maxx=maxx,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            if text:
                samples.append(elapsed)
                successes += 1
            else:
                error_samples.append(elapsed)
            print(
                f"    [fast_rag]   iter={i + 1}/{ITERS} maxx={maxx:<9} "
                f"chunks={len(chunks):>2} len={len(text or ''):>4} {elapsed:>7.0f}ms  q={q[:40]!r}"
            )
        except Exception as e:
            print(f"    [fast_rag]   iter={i + 1}/{ITERS} FAILED: {e}")
        if SLEEP_BETWEEN and i < ITERS - 1:
            await asyncio.sleep(SLEEP_BETWEEN)
    print(f"    [fast_rag]   successes={successes}/{ITERS}")
    _report("fast_rag.answer_from_rag", samples)


async def bench_graph_knowledge() -> None:
    lc_graph.rebuild_graph()
    samples: list[float] = []
    successes = 0
    for i in range(ITERS):
        maxx, q = KNOWLEDGE_QUERIES[i % len(KNOWLEDGE_QUERIES)]
        # Verify classifier routes to KNOWLEDGE for transparency
        cls = classify_turn(q, active_maxx=maxx)
        t0 = time.perf_counter()
        try:
            result = await lc_graph.run_graph_chat(
                message=q,
                history=[],
                user_context={"coaching_context": "", "active_schedule": None, "onboarding": {"timezone": "UTC"}},
                user_id="00000000-0000-0000-0000-000000000000",
                make_tools=lambda: [],
                maxx_id=maxx,
                active_maxx=maxx,
                channel="app",
            )
            elapsed = (time.perf_counter() - t0) * 1000
            if result.get("response"):
                samples.append(elapsed)
                successes += 1
            tel = result.get("telemetry", {})
            print(
                f"    [graph_know] iter={i + 1}/{ITERS} maxx={maxx:<9} "
                f"intent={result.get('intent'):<11} chunks={len(result.get('retrieved') or []):>2} "
                f"len={len(result.get('response') or ''):>4} {elapsed:>7.0f}ms  "
                f"retrieve={tel.get('retrieve', 0):.0f}ms knowledge={tel.get('knowledge_answer', 0):.0f}ms"
            )
        except Exception as e:
            print(f"    [graph_know] iter={i + 1}/{ITERS} FAILED: {e}")
        if SLEEP_BETWEEN and i < ITERS - 1:
            await asyncio.sleep(SLEEP_BETWEEN)
    print(f"    [graph_know] successes={successes}/{ITERS}  (classifier routed {maxx}/{q[:40]!r} as {cls['intent']})")
    _report("lc_graph.KNOWLEDGE", samples)


async def bench_graph_other() -> None:
    """Agent path — skip tools so we measure pure LLM synthesis time."""
    lc_graph.rebuild_graph()
    samples: list[float] = []
    successes = 0
    for i in range(ITERS):
        q = OTHER_QUERIES[i % len(OTHER_QUERIES)]
        cls = classify_turn(q, active_maxx="skinmax")
        t0 = time.perf_counter()
        try:
            result = await lc_graph.run_graph_chat(
                message=q,
                history=[],
                user_context={"coaching_context": "user has active skinmax schedule.", "active_schedule": None, "onboarding": {"timezone": "UTC"}},
                user_id="00000000-0000-0000-0000-000000000000",
                make_tools=lambda: [],   # no tools so the agent replies directly
                maxx_id="skinmax",
                active_maxx="skinmax",
                channel="app",
            )
            elapsed = (time.perf_counter() - t0) * 1000
            if result.get("response"):
                samples.append(elapsed)
                successes += 1
            tel = result.get("telemetry", {})
            print(
                f"    [graph_other] iter={i + 1}/{ITERS} intent={result.get('intent'):<11} "
                f"len={len(result.get('response') or ''):>4} {elapsed:>7.0f}ms  "
                f"agent={tel.get('agent', 0):.0f}ms  q={q[:40]!r}"
            )
        except Exception as e:
            print(f"    [graph_other] iter={i + 1}/{ITERS} FAILED: {e}")
        if SLEEP_BETWEEN and i < ITERS - 1:
            await asyncio.sleep(SLEEP_BETWEEN)
    print(f"    [graph_other] successes={successes}/{ITERS}  (last classify={cls['intent']})")
    _report("lc_graph.OTHER (agent, no tools)", samples)


async def main() -> None:
    print("\n=== RAG END-TO-END BENCHMARK (with real LLM calls) ===")
    print(f"Provider: {settings.llm_provider!r}  gemini_key={'set' if settings.gemini_api_key else 'EMPTY'}"
          f"  openai_key={'set' if settings.openai_api_key else 'EMPTY'}")
    print(f"Iterations per path: {ITERS}\n")

    await warm_indexes()

    print("[1/3] Direct fast-path RAG (retrieve + LLM answer)")
    await bench_fast_rag()

    print("\n[2/3] LangGraph KNOWLEDGE node (full graph, then knowledge_answer)")
    await bench_graph_knowledge()

    print("\n[3/3] LangGraph OTHER intent (agent path, no tools)")
    await bench_graph_other()

    print()


if __name__ == "__main__":
    asyncio.run(main())
