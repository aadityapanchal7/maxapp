"""
Maxes API - Looksmaxxing programs (fitmax, skinmax, etc.)

The canonical source of truth lives in `services.maxx_guidelines.MAXX_GUIDELINES`.
The RDS `maxes` table is a denormalized cache for the mobile UI; if RDS is
unreachable (local dev without RDS creds, or production hiccup) we serve the
in-process guidelines instead so the app never sees missing labels/descriptions.
"""

from __future__ import annotations

from typing import Any, Optional

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_rds_db_optional
from middleware.auth_middleware import get_current_user
from models.rds_models import Maxx
from services.maxx_guidelines import MAXX_GUIDELINES, get_maxx_guideline

router = APIRouter(prefix="/maxes", tags=["Maxes"])

# The maxx catalog is GLOBAL (5 rows, identical for every user) and only changes
# on a deploy or an RDS seed. Home, Explore, Profile and the prefetcher all pull
# it, so un-cached it was a per-user round trip for constant data. 15-minute TTL;
# an RDS re-seed shows up within that window.
_LIST_TTL_SECONDS = 900.0
_list_cache: dict | None = None
_list_cached_at: float = 0.0


# Display metadata kept here (not in MAXX_GUIDELINES) — matches scripts/sync_maxes_guidelines_to_rds.py.
_DISPLAY: dict[str, dict[str, str]] = {
    "skinmax":   {"icon": "sparkles-outline", "color": "#8B5CF6"},
    "hairmax":   {"icon": "cut-outline",      "color": "#3B82F6"},
    "fitmax":    {"icon": "fitness-outline",  "color": "#10B981"},
    "heightmax": {"icon": "resize-outline",   "color": "#6366F1"},
    "bonemax":   {"icon": "body-outline",     "color": "#F59E0B"},
}


@router.get("")
async def list_maxes(
    current_user: dict = Depends(get_current_user),
    rds_db: Optional[AsyncSession] = Depends(get_rds_db_optional),
):
    """Return all active maxxes. RDS-backed when available, falls back to
    services.maxx_guidelines (the same data RDS is seeded from) otherwise."""
    global _list_cache, _list_cached_at
    if _list_cache is not None and (time.monotonic() - _list_cached_at) < _LIST_TTL_SECONDS:
        return _list_cache

    payload: dict | None = None
    if rds_db is not None:
        try:
            result = await rds_db.execute(select(Maxx).where(Maxx.is_active == True))
            rows = result.scalars().all()
            if rows:
                payload = {"maxes": [_serialize_row(m) for m in rows]}
        except Exception:
            # Connection / query failure — degrade gracefully.
            pass
    if payload is None:
        payload = {"maxes": [_serialize_fallback(mid) for mid in _DISPLAY]}

    _list_cache = payload
    _list_cached_at = time.monotonic()
    return payload


@router.get("/{maxx_id}")
async def get_maxx(
    maxx_id: str,
    current_user: dict = Depends(get_current_user),
    rds_db: Optional[AsyncSession] = Depends(get_rds_db_optional),
):
    """Return a single maxx by id (e.g. 'fitmax')"""
    if rds_db is not None:
        try:
            result = await rds_db.execute(select(Maxx).where(Maxx.id == maxx_id))
            row = result.scalar_one_or_none()
            if row is not None:
                return _serialize_row(row)
        except Exception:
            pass
    if maxx_id not in MAXX_GUIDELINES:
        raise HTTPException(status_code=404, detail="Maxx not found")
    return _serialize_fallback(maxx_id)


# --------------------------------------------------------------------------- #
#  Serialization                                                              #
# --------------------------------------------------------------------------- #

def _serialize_row(m: Maxx) -> dict[str, Any]:
    fallback = get_maxx_guideline(m.id) or {}
    label = m.label
    description = m.description
    # Canonical product copy (RDS rows may be stale until re-seeded).
    if m.id == "skinmax":
        label = "Skinmax"
        description = "skincare and your inner glow"
    if not description:
        description = fallback.get("description") or ""
    return {
        "id": m.id,
        "label": label,
        "description": description,
        "icon": m.icon or _DISPLAY.get(m.id, {}).get("icon"),
        "color": m.color or _DISPLAY.get(m.id, {}).get("color"),
        "modules": m.modules or fallback.get("modules", []),
        "protocols": m.protocols or fallback.get("protocols", {}),
        "concerns": m.concerns or fallback.get("concerns", []),
        "concern_question": m.concern_question or fallback.get("concern_question"),
        "is_active": m.is_active,
        "created_at": m.created_at,
    }


def _serialize_fallback(maxx_id: str) -> dict[str, Any]:
    """Build the same shape as _serialize_row, sourced from in-process guidelines."""
    g = MAXX_GUIDELINES.get(maxx_id) or {}
    meta = _DISPLAY.get(maxx_id, {})
    label = g.get("label") or maxx_id
    description = g.get("description") or ""
    if maxx_id == "skinmax":
        label = "Skinmax"
        description = "skincare and your inner glow"
    return {
        "id": maxx_id,
        "label": label,
        "description": description,
        "icon": meta.get("icon"),
        "color": meta.get("color"),
        "modules": g.get("modules", []),
        "protocols": g.get("protocols", {}),
        "concerns": g.get("concerns", []),
        "concern_question": g.get("concern_question"),
        "is_active": True,
        "created_at": None,
    }
