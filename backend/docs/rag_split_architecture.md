# Split-Path RAG Architecture

## Overview

The chat stack now has a strict split:

- `KNOWLEDGE` turns: `classify -> retrieve -> answer`
- everything else: `classify -> scoped context -> optional retrieval -> agent`

Knowledge turns do **not** build the full coaching context and do **not** enter the LangChain agent.

## Retrieval

The live retriever is file-based BM25 over:

- `rag_docs/<maxx_id>` as the canonical source
- `backend/rag_content/<maxx_id>` as legacy fallback content

Each chunk now carries a stable file-based audit identifier, persisted into `chat_history.retrieved_chunk_ids` as JSON.

## Context Budgets

Prompt bloat is constrained at three layers:

- `chat_max_coaching_context_tokens`: hard cap on the serialized `coaching_context`
- `chat_max_system_prompt_tokens`: hard cap on the final system prompt after injection
- `chat_max_context_tokens`: graph trim budget for history + retrieved chunks

`build_full_context()` is now intent-scoped. Greeting and knowledge-adjacent turns skip schedule/task/module-engine loading. Check-in and schedule flows still load the richer schedule context they need.

## Memory Model

Prompt memory is now split into:

- structured `MEMORY SLOTS` for durable facts like goals, injuries, tolerances, and tone
- a short `RECENT MEMORY SUMMARY` for narrative carry-over

This keeps persistent user facts available without dumping large prose summaries into every prompt.

## LangGraph

LangGraph now has a dedicated `knowledge_answer` node. Knowledge turns retrieve evidence and answer directly from chunks, bypassing the agent completely.

## Telemetry

Structured telemetry now logs:

- context build latency and section composition
- retrieval latency and hit counts
- prompt token budgets split by system/context/history/chunks/user
- agent iteration counts
- fast-path hit rate

## Retrieval Threshold

`rag_score_threshold` (default `0.35`) in `config.py` is the single source of truth. Call sites that previously hardcoded a threshold (`fast_product_links.py`) now read from settings.

## Test Coverage

The `backend/tests/` suite covers:

- `test_chat_routing.py` — KNOWLEDGE bypass at the chat API and LangGraph layers
- `test_context_builder.py` — intent-scoped context requirements and schedule-query gating
- `test_fast_rag_and_retriever.py` — BM25 stable IDs, threshold respect, and citation preservation
- `test_retriever_unified.py` — tokenization, chunk-ID stability, empty/unknown guards, metadata audit fields, and retrieval telemetry
- `test_token_budgets.py` — hard caps on context blob, history/chunk trimming, and bounded agent system prompt
- `test_chunk_audit.py` — file-based chunk identifier formats persisted to `chat_history.retrieved_chunk_ids`
- `test_chat_telemetry.py` — structured log emission for every telemetry point
