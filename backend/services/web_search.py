"""Tiny web-search fallback service.

Used by the chat agent ONLY when the doc-RAG layer can't answer — the
agent's system prompt tells it to call `web_search` as a last resort
(see services.lc_agent).

Backend: DuckDuckGo via the `ddgs` package — free, no API key, ~300-700ms
per query. Results are cached in-memory for 1 hour so identical queries
in a chat session don't re-hit the network.

Notes:
- Returns a tight, model-friendly summary string (title · snippet · url),
  not raw HTML or JSON.  The agent gets exactly what it needs to ground
  a one-paragraph answer.
- Hard-capped to 3 results × ~250 char snippets so a single call adds
  only ~600-800 input tokens to the agent's next thought.
- Failure is graceful — returns a short "search unavailable" string
  rather than raising, so a flaky network doesn't kill the whole turn.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL_S = 3600.0
_CACHE_MAX = 256


def _cache_key(query: str, max_results: int) -> str:
    h = hashlib.sha1(f"{query.strip().lower()}|{max_results}".encode()).hexdigest()
    return h[:16]


async def search(query: str, *, max_results: int = 3, region: Optional[str] = None) -> str:
    """Run a web search and return a compact result string.

    Output format (one block per result, blank line between):
        1. <title>
           <snippet>
           <url>

    Returns "" on empty query, a friendly string on failure.
    """
    q = (query or "").strip()
    if not q:
        return ""
    if len(q) > 200:
        q = q[:200]
    n = max(1, min(5, int(max_results)))

    key = _cache_key(q, n)
    cached = _CACHE.get(key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL_S:
        return cached[1]

    try:
        # ddgs has a sync API; run it in a thread so we don't block the
        # async event loop.
        results = await asyncio.wait_for(
            asyncio.to_thread(_ddg_search, q, n, region),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        logger.info("web search timed out for %r", q)
        return f"(web search timed out for: {q})"
    except Exception as e:
        logger.info("web search failed for %r: %s", q, e)
        return f"(web search unavailable: {e.__class__.__name__})"

    if not results:
        out = f"(no web results for: {q})"
    else:
        lines: list[str] = []
        for i, r in enumerate(results[:n], start=1):
            title = (r.get("title") or "").strip()[:140]
            body = (r.get("body") or r.get("snippet") or "").strip().replace("\n", " ")[:260]
            url = (r.get("href") or r.get("url") or "").strip()
            lines.append(f"{i}. {title}\n   {body}\n   {url}")
        out = "\n\n".join(lines)

    # LRU-ish: insert + cap.
    _CACHE[key] = (time.time(), out)
    if len(_CACHE) > _CACHE_MAX:
        # Drop oldest 25%.
        ranked = sorted(_CACHE.items(), key=lambda kv: kv[1][0])
        for k, _ in ranked[: len(_CACHE) // 4]:
            _CACHE.pop(k, None)
    return out


def _ddg_search(query: str, max_results: int, region: Optional[str]) -> list[dict]:
    """Sync DDG call (runs in a thread). Imported lazily so import-time
    failures here don't block the chat module."""
    from ddgs import DDGS
    kwargs = {"max_results": max_results}
    if region:
        kwargs["region"] = region
    with DDGS() as d:
        return list(d.text(query, **kwargs))
