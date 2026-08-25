"""Public runtime config for the mobile app (feature flags).

Feature flags live as a JSON object in the `system_prompts` table under the key
`feature_flags_json` — reusing the same DB-driven mechanism as the LLM prompts, so
flags can be toggled straight from the DB with NO app rebuild and NO backend
redeploy. The client merges whatever this returns OVER its built-in defaults, so
the endpoint is purely an override: on any error / missing row it returns `{}` and
the app behaves exactly as before.
"""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models.sqlalchemy_models import SystemPrompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])

# Every app fetches this at boot and re-checks every 5 minutes, and the answer is
# the SAME global row for every user. Un-cached that was one cross-region DB
# round trip per client per 5 min — pure waste on data that changes when someone
# edits a row by hand. 60s TTL keeps flag flips feeling instant (they still
# propagate within a minute) while collapsing the fleet's reads to ~1/min.
_FLAGS_TTL_SECONDS = 60.0
_flags_cache: dict | None = None
_flags_cached_at: float = 0.0


@router.get("/flags")
async def get_feature_flags(db: AsyncSession = Depends(get_db)) -> dict:
    """Feature-flag overrides as ``{flagName: bool}``.

    Returns ``{}`` (client falls back to its built-in defaults) on a missing row,
    malformed JSON, or any DB error — flags must never be able to break the app.
    Served from a short in-process TTL cache (see _FLAGS_TTL_SECONDS).
    """
    global _flags_cache, _flags_cached_at
    if _flags_cache is not None and (time.monotonic() - _flags_cached_at) < _FLAGS_TTL_SECONDS:
        return _flags_cache
    try:
        content = (
            await db.execute(
                select(SystemPrompt.content).where(
                    SystemPrompt.key == "feature_flags_json",
                    SystemPrompt.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if not content:
            return _remember({})
        data = json.loads(content)
        if not isinstance(data, dict):
            return _remember({})
        # Defensive: only surface real booleans, ignore anything else.
        return _remember({k: bool(v) for k, v in data.items() if isinstance(v, bool)})
    except Exception as exc:  # never break the client over a flag lookup
        logger.warning("get_feature_flags failed, returning {}: %s", exc)
        # Deliberately NOT cached: a transient DB blip must not pin empty flags
        # for the whole TTL. Serve the last good value if we have one.
        return _flags_cache if _flags_cache is not None else {}


def _remember(flags: dict) -> dict:
    global _flags_cache, _flags_cached_at
    _flags_cache = flags
    _flags_cached_at = time.monotonic()
    return flags
