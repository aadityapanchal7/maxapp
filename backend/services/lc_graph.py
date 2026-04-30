"""LangGraph chat orchestration — explicit nodes, observable, testable.

Nodes
=====
    guardrail  ─┬─ blocked  ────────────────────────►  END (canned response)
                └─ pass     ─► classify
    classify   ─┬─ needs_rag ─► retrieve ─► trim ─► agent ─► finalize ─► END
                └─ skip_rag  ────────────────► trim ─► agent ─► finalize ─► END

State carries the raw inputs, classifier output, retrieved chunks, trimmed history,
final response, and per-node telemetry. chat.py consumes the final state and
handles DB persistence (chat_history, audit columns) so the graph stays pure-ish.

Why this instead of the bare AgentExecutor:
- Intent classification skips RAG retrieval + the cheap path wins ~500ms on
  check-in / greeting turns (majority of traffic on active users).
- Guardrail node catches "ignore previous instructions" before it costs an LLM call.
- Trim node keeps prompt size under control regardless of how long the thread grows.
- Telemetry per node exposes which step slowed down a turn — impossible in the
  AgentExecutor black box.
- Future-proof: adding a "human-in-the-loop approval" gate for irreversible tool
  calls is one extra conditional edge.

Feature-flagged — enable with CHAT_USE_LANGGRAPH=true in .env.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Optional, TypedDict

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.chat_telemetry import fast_path_snapshot
from services.fast_rag_answer import answer_from_chunks
from services.intent_classifier import classify_turn, is_injection_attempt
from services.token_budget import trim_chunks, trim_history, summarize_usage

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Graph state                                                                 #
# --------------------------------------------------------------------------- #

class ChatState(TypedDict, total=False):
    # --- inputs (set by caller) ---
    message: str
    history: list[dict]
    user_id: str
    maxx_id: Optional[str]
    active_maxx: Optional[str]
    channel: str
    image_data: Optional[bytes]
    user_context: dict
    make_tools: Any                     # callable -> list[Tool]; runs once we know intent
    # --- set by nodes ---
    guardrail_verdict: str              # "pass" | "block"
    intent: str
    maxx_hints: list[str]
    skip_rag: bool
    confidence: str
    retrieved: list[dict]
    trimmed_history: list[dict]
    response: str
    schedule_mutated: bool
    telemetry: dict[str, float]
    short_circuit_reason: Optional[str]


# --------------------------------------------------------------------------- #
#  Nodes                                                                       #
# --------------------------------------------------------------------------- #

_BLOCKED_RESPONSE = (
    "i can't help with that — looks like a prompt-injection attempt. "
    "if you have a real question about your routine, ask it directly."
)


def _time(state: ChatState, key: str, start: float) -> None:
    """Record elapsed ms for a node into telemetry."""
    tel = state.setdefault("telemetry", {})
    tel[key] = round((time.perf_counter() - start) * 1000, 1)


async def guardrail_node(state: ChatState) -> ChatState:
    """Block obvious prompt-injection attempts before they cost an LLM call."""
    t0 = time.perf_counter()
    if is_injection_attempt(state.get("message", "")):
        state["guardrail_verdict"] = "block"
        state["response"] = _BLOCKED_RESPONSE
        state["short_circuit_reason"] = "prompt_injection"
    else:
        state["guardrail_verdict"] = "pass"
    _time(state, "guardrail", t0)
    return state


async def classify_node(state: ChatState) -> ChatState:
    t0 = time.perf_counter()
    result = classify_turn(state.get("message", ""), active_maxx=state.get("active_maxx"))
    state["intent"] = result["intent"]
    state["maxx_hints"] = result["maxx_hints"]
    state["skip_rag"] = result["skip_rag"]
    state["confidence"] = result["confidence"]
    _time(state, "classify", t0)
    logger.info(
        "[GRAPH] intent=%s maxx_hints=%s skip_rag=%s conf=%s",
        result["intent"], result["maxx_hints"], result["skip_rag"], result["confidence"],
    )
    return state


async def retrieve_node(state: ChatState) -> ChatState:
    """Fan-out retrieval across maxx_hints in parallel. Empty hints → no retrieval."""
    t0 = time.perf_counter()
    from services.rag_service import retrieve_chunks

    message = state.get("message", "") or ""
    hints = state.get("maxx_hints") or []
    if not hints and state.get("active_maxx"):
        hints = [state["active_maxx"]]

    if not hints:
        state["retrieved"] = []
        _time(state, "retrieve", t0)
        return state

    k_per_maxx = max(2, int(getattr(settings, "rag_top_k", 4) or 4) // max(1, len(hints)) + 1)
    min_similarity = float(getattr(settings, "rag_score_threshold", 0.35) or 0.35)

    async def _one(maxx: str) -> list[dict]:
        try:
            return await retrieve_chunks(
                None,
                maxx,
                message,
                k=k_per_maxx,
                min_similarity=min_similarity,
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("retrieve_chunks failed for %s: %s", maxx, e)
            return []

    results_per_maxx = await asyncio.gather(*[_one(m) for m in hints])

    # Interleave top chunks across maxxes, then trim by global top_k by score
    merged: list[dict] = []
    for hint, row_set in zip(hints, results_per_maxx):
        for i, chunk in enumerate(row_set):
            # preserve origin for logs
            chunk = {**chunk, "_maxx": chunk.get("_maxx") or hint}
            merged.append(chunk)
    merged.sort(key=lambda c: c.get("similarity", 0.0), reverse=True)
    state["retrieved"] = merged[: int(getattr(settings, "rag_top_k", 4) or 4)]
    _time(state, "retrieve", t0)
    logger.info("[GRAPH] retrieved %d chunks from %s", len(state["retrieved"]), hints)
    return state


async def knowledge_answer_node(state: ChatState) -> ChatState:
    """Direct answer path for knowledge turns; skips the agent entirely."""
    t0 = time.perf_counter()
    ob = ((state.get("user_context") or {}).get("onboarding") or {}) if isinstance(state.get("user_context"), dict) else {}
    length_pref = str(ob.get("response_length") or "").strip().lower() or None
    state["response"] = await answer_from_chunks(
        message=state.get("message", ""),
        retrieved=state.get("retrieved") or [],
        maxx_hints=state.get("maxx_hints") or [],
        active_maxx=state.get("active_maxx"),
        response_length=length_pref,
    )
    if not (state.get("response") or "").strip():
        state["response"] = "i don't have that in the course material yet."
    state["schedule_mutated"] = False
    fast_path_snapshot("graph_knowledge")
    _time(state, "knowledge_answer", t0)
    return state


async def trim_node(state: ChatState) -> ChatState:
    """Trim chat history + retrieved chunks to fit the token budget."""
    t0 = time.perf_counter()
    max_ctx = int(getattr(settings, "chat_max_context_tokens", 8000) or 8000)

    # Split budget: ~60% to history, ~25% to retrieved, rest to system+user+overhead
    history_budget = int(max_ctx * 0.60)
    chunks_budget = int(max_ctx * 0.25)

    history = state.get("history") or []
    retrieved = state.get("retrieved") or []

    state["trimmed_history"] = trim_history(history, max_tokens=history_budget, keep_last=4)
    state["retrieved"] = trim_chunks(retrieved, max_tokens=chunks_budget)
    _time(state, "trim", t0)
    return state


async def agent_node(state: ChatState) -> ChatState:
    """Delegate to the existing tool-calling agent. Inject retrieved chunks into
    user_context.coaching_context so the agent's system prompt renders them."""
    from services.lc_agent import run_chat_agent
    from services.lc_memory import history_dicts_to_lc_messages

    t0 = time.perf_counter()

    user_context = dict(state.get("user_context") or {})
    chunks = state.get("retrieved") or []
    if chunks:
        lines = ["[COURSE CONTEXT — ground answers in this when the user asks about the course. "
                 "If the answer isn't here, say so rather than guessing.]"]
        for i, c in enumerate(chunks, 1):
            title = c.get("doc_title") or "chunk"
            sim = c.get("similarity") or 0.0
            src = c.get("_maxx") or ""
            lines.append(f"\n--- {i}. {title} ({src} sim={sim:.2f}) ---\n{c.get('content','').strip()}")
        ctx_block = "\n".join(lines)
        existing = user_context.get("coaching_context") or ""
        user_context["coaching_context"] = (existing + "\n\n" + ctx_block).strip()

    make_tools = state.get("make_tools")
    tools = make_tools() if callable(make_tools) else []
    lc_history = history_dicts_to_lc_messages(state.get("trimmed_history") or [])

    try:
        response, mutated = await run_chat_agent(
            message=state.get("message", ""),
            lc_history=lc_history,
            user_context=user_context,
            image_data=state.get("image_data"),
            delivery_channel=state.get("channel", "app"),
            tools=tools,
            db=None,   # real db already bound inside tool closures in make_tools()
            maxx_id=state.get("maxx_id"),
        )
        state["response"] = response
        state["schedule_mutated"] = mutated
    except Exception as e:
        logger.exception("agent_node failed: %s", e)
        state["response"] = ""
        state["schedule_mutated"] = False
    _time(state, "agent", t0)
    return state


async def finalize_node(state: ChatState) -> ChatState:
    """Enforce response conventions + log a single structured telemetry line."""
    t0 = time.perf_counter()
    resp = (state.get("response") or "").strip()
    if resp:
        state["response"] = resp.lower() if state.get("channel") == "app" else resp

    # Token accounting for telemetry
    usage = summarize_usage(
        system="",  # agent owns it, not worth recomputing here
        history=state.get("trimmed_history") or [],
        chunks=state.get("retrieved") or [],
        user_msg=state.get("message", ""),
    )
    tel = state.setdefault("telemetry", {})
    tel.update({
        "history_tokens": usage["history"],
        "retrieved_tokens": usage["retrieved"],
        "user_tokens": usage["user"],
    })
    _time(state, "finalize", t0)

    logger.info(
        "[GRAPH] user=%s intent=%s chunks=%d mutated=%s resp_len=%d timings_ms=%s",
        str(state.get("user_id", ""))[:8],
        state.get("intent"),
        len(state.get("retrieved") or []),
        state.get("schedule_mutated"),
        len(state.get("response") or ""),
        state.get("telemetry"),
    )
    return state


# --------------------------------------------------------------------------- #
#  Graph wiring                                                                #
# --------------------------------------------------------------------------- #

def _should_retrieve(state: ChatState) -> str:
    return "retrieve" if not state.get("skip_rag") else "trim"


def _guardrail_router(state: ChatState) -> str:
    return "end" if state.get("guardrail_verdict") == "block" else "classify"


def _post_retrieve_router(state: ChatState) -> str:
    return "knowledge_answer" if state.get("intent") == "KNOWLEDGE" else "trim"


_compiled_graph = None


def build_graph():
    """Compile (and memoise) the LangGraph app. Rebuild via rebuild_graph() if needed."""
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    from langgraph.graph import StateGraph, START, END

    g = StateGraph(ChatState)
    g.add_node("guardrail", guardrail_node)
    g.add_node("classify", classify_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("knowledge_answer", knowledge_answer_node)
    g.add_node("trim", trim_node)
    g.add_node("agent", agent_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "guardrail")
    g.add_conditional_edges("guardrail", _guardrail_router, {"classify": "classify", "end": "finalize"})
    g.add_conditional_edges("classify", _should_retrieve, {"retrieve": "retrieve", "trim": "trim"})
    g.add_conditional_edges("retrieve", _post_retrieve_router, {"knowledge_answer": "knowledge_answer", "trim": "trim"})
    g.add_edge("knowledge_answer", "finalize")
    g.add_edge("trim", "agent")
    g.add_edge("agent", "finalize")
    g.add_edge("finalize", END)

    _compiled_graph = g.compile()
    return _compiled_graph


def rebuild_graph() -> None:
    """Force recompile — useful in tests or after hot-reloading nodes."""
    global _compiled_graph
    _compiled_graph = None


# --------------------------------------------------------------------------- #
#  Public entry point                                                          #
# --------------------------------------------------------------------------- #

async def run_graph_chat(
    *,
    message: str,
    history: list[dict],
    user_context: dict,
    user_id: str,
    make_tools,                 # callable returning the list[Tool] for this turn
    maxx_id: Optional[str] = None,
    active_maxx: Optional[str] = None,
    channel: str = "app",
    image_data: Optional[bytes] = None,
) -> dict:
    """Run one chat turn through the graph. Returns a dict chat.py can consume.

    The tuple contract (response, schedule_mutated) is preserved in the
    `response` and `schedule_mutated` keys for backward compatibility, plus
    extras: `retrieved`, `intent`, `telemetry`.
    """
    app = build_graph()

    init: ChatState = {
        "message": message,
        "history": history or [],
        "user_id": user_id,
        "maxx_id": maxx_id,
        "active_maxx": active_maxx,
        "channel": channel,
        "image_data": image_data,
        "user_context": user_context or {},
        "make_tools": make_tools,
    }

    try:
        final: ChatState = await app.ainvoke(init)  # type: ignore[assignment]
    except Exception as e:
        logger.exception("graph ainvoke failed: %s", e)
        raise

    return {
        "response": final.get("response") or "",
        "schedule_mutated": bool(final.get("schedule_mutated")),
        "retrieved": final.get("retrieved") or [],
        "intent": final.get("intent") or "UNKNOWN",
        "telemetry": final.get("telemetry") or {},
        "short_circuit_reason": final.get("short_circuit_reason"),
    }
