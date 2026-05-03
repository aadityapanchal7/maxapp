"""In-memory task catalog cache.

The schedule generator reads from this cache, NOT from the DB on the
hot path. Cache is loaded once at startup (warm_catalog) and rebuilt
on demand via reload_catalog() after ingest.

Loading from disk (data/maxes/*.md) is the source of truth — the DB
copy in `task_catalog` exists for parity with RAG and for read-only
access from other services. If the on-disk file disagrees with the DB
row, the on-disk file wins on next ingest.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from services.max_doc_loader import MaxDoc, TaskDef, parse_all_max_docs
from services.schedule_dsl import evaluate_all, evaluate_any

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  In-memory cache                                                            #
# --------------------------------------------------------------------------- #

@dataclass
class _Entry:
    doc: MaxDoc
    by_id: dict[str, TaskDef]


_CACHE: dict[str, _Entry] = {}
_CACHE_LOAD_TS: float = 0.0
_LOCK = asyncio.Lock()


async def warm_catalog() -> None:
    """Load every max doc into memory. Call from app startup."""
    async with _LOCK:
        await _load()


async def reload_catalog() -> None:
    """Force reload (e.g. after `ingest_max_docs` runs)."""
    async with _LOCK:
        _CACHE.clear()
        await _load()


async def _load() -> None:
    global _CACHE_LOAD_TS
    t0 = time.perf_counter()
    docs = await asyncio.to_thread(parse_all_max_docs)
    for doc in docs:
        _CACHE[doc.maxx_id] = _Entry(
            doc=doc,
            by_id={t.id: t for t in doc.tasks},
        )
    _CACHE_LOAD_TS = time.time()
    logger.info(
        "task_catalog: loaded %d maxes (%d total tasks) in %.0fms",
        len(_CACHE),
        sum(len(e.by_id) for e in _CACHE.values()),
        (time.perf_counter() - t0) * 1000,
    )


def get_doc(maxx_id: str) -> Optional[MaxDoc]:
    e = _CACHE.get(maxx_id)
    return e.doc if e else None


def get_task(maxx_id: str, task_id: str) -> Optional[TaskDef]:
    e = _CACHE.get(maxx_id)
    return e.by_id.get(task_id) if e else None


def all_tasks(maxx_id: str) -> list[TaskDef]:
    e = _CACHE.get(maxx_id)
    return list(e.by_id.values()) if e else []


def is_loaded() -> bool:
    return bool(_CACHE)


def loaded_maxes() -> list[str]:
    return sorted(_CACHE.keys())


# --------------------------------------------------------------------------- #
#  Filtering: which tasks apply to this user / phase?                         #
# --------------------------------------------------------------------------- #

def eligible_tasks(
    maxx_id: str,
    user_ctx: dict[str, Any],
    *,
    intensity_cap: float = 1.0,
) -> list[TaskDef]:
    """Return tasks whose applies_when is true AND contraindicated_when is
    false AND intensity ≤ cap. The generator picks from this filtered set
    so the LLM can't choose a task that conflicts with the user state.
    """
    out: list[TaskDef] = []
    for task in all_tasks(maxx_id):
        if task.intensity > intensity_cap + 1e-6:
            continue
        if task.contraindicated_when and evaluate_any(task.contraindicated_when, user_ctx):
            continue
        if not evaluate_all(task.applies_when, user_ctx):
            continue
        out.append(task)
    return out


def required_field_ids(maxx_id: str) -> list[str]:
    """Field IDs the bot MUST collect before generating for this max."""
    doc = get_doc(maxx_id)
    if not doc:
        return []
    return [str(f["id"]) for f in doc.required_fields if f.get("required", True)]


def missing_required(maxx_id: str, user_ctx: dict[str, Any]) -> list[dict]:
    """Return the field-spec dicts for any required field not yet
    answered. The bot uses these to drive the next question(s)."""
    doc = get_doc(maxx_id)
    if not doc:
        return []
    out: list[dict] = []
    for f in doc.required_fields:
        if not f.get("required", True):
            continue
        fid = f.get("id")
        if not fid:
            continue
        v = user_ctx.get(fid)
        if v is None or (isinstance(v, str) and not v.strip()):
            out.append(f)
    return out


def applicable_modifiers(maxx_id: str, user_ctx: dict[str, Any]) -> list[str]:
    """Return the `then:` strings of every prompt_modifier whose
    condition fires. Order matches doc declaration."""
    doc = get_doc(maxx_id)
    if not doc:
        return []
    out: list[str] = []
    for mod in doc.prompt_modifiers:
        cond = mod.get("if") or "always"
        if evaluate_all([cond], user_ctx):
            then = mod.get("then")
            if then:
                out.append(str(then))
    return out
