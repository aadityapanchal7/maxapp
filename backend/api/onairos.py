"""Onairos personalization — per-user consent handoff + traits API.

Flow:
    1. Mobile runs the Onairos SDK consent UI (`@onairos/react-native`).
    2. SDK's onResolved returns `{apiUrl, accessToken, approvedRequests, userData?}`.
    3. Mobile POSTs that payload to `POST /api/onairos/connect`.
    4. Backend persists the handoff and best-effort fetches an initial trait
       snapshot so the coaching context builder can start using it immediately.
    5. Subsequent `POST /api/onairos/refresh-traits` calls re-pull the snapshot.
    6. `DELETE /api/onairos/disconnect` revokes the connection (coaching stops
       using the trait slot).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from middleware import get_current_user
from services.onairos_service import onairos_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onairos", tags=["Onairos"])


class OnairosConnectBody(BaseModel):
    api_url: str = Field(..., alias="apiUrl", description="Inference endpoint returned by the SDK")
    access_token: str = Field(..., alias="accessToken", description="Short-lived domain JWT")
    approved_requests: dict[str, Any] = Field(
        default_factory=dict,
        alias="approvedRequests",
        description="Which consent categories the user approved",
    )
    user_basic: Optional[dict[str, Any]] = Field(
        default=None,
        alias="userData",
        description="Optional basic user info (name, email) returned by the SDK",
    )

    class Config:
        populate_by_name = True


class OnairosStatusResponse(BaseModel):
    connected: bool
    connected_at: Optional[str] = None
    token_expires_at: Optional[str] = None
    traits_cached_at: Optional[str] = None
    approved_requests: dict[str, Any] = Field(default_factory=dict)
    traits: Optional[dict[str, Any]] = None


def _iso(ts) -> Optional[str]:
    return ts.isoformat() if ts else None


@router.post("/connect", status_code=status.HTTP_200_OK)
async def connect(
    body: OnairosConnectBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Persist the SDK handoff and kick off the first trait sync."""
    if not body.api_url.strip() or not body.access_token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="apiUrl and accessToken are required",
        )

    user_id = str(current_user["id"])
    await onairos_service.save_handoff(
        user_id,
        db,
        api_url=body.api_url.strip(),
        access_token=body.access_token.strip(),
        approved_requests=body.approved_requests,
        user_basic=body.user_basic,
    )

    # Best-effort initial traits fetch. If Onairos is slow or down, we still
    # return success — the client already has its consent recorded and a
    # later /refresh-traits will pick it up.
    traits: Optional[dict[str, Any]] = None
    try:
        traits = await onairos_service.refresh_traits(user_id, db)
    except Exception as e:
        logger.warning("initial onairos refresh failed for user=%s: %s", user_id, e)

    # Invalidate coaching context cache so the next chat turn picks up the
    # new trait slot immediately.
    try:
        from services.coaching_service import coaching_service
        coaching_service.invalidate_context_cache(user_id)
    except Exception:
        pass

    return {"ok": True, "initial_traits": traits}


@router.post("/refresh-traits")
async def refresh_traits(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Pull the latest Onairos trait snapshot for this user and cache it."""
    user_id = str(current_user["id"])
    conn = await onairos_service.get_connection(user_id, db)
    if conn is None or conn.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Onairos connection for this user",
        )
    traits = await onairos_service.refresh_traits(user_id, db)
    if traits is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Onairos inference call failed",
        )
    try:
        from services.coaching_service import coaching_service
        coaching_service.invalidate_context_cache(user_id)
    except Exception:
        pass
    return {"ok": True, "traits": traits}


@router.get("/status", response_model=OnairosStatusResponse)
async def status_endpoint(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnairosStatusResponse:
    """Report whether the current user has an active connection and its freshness."""
    user_id = str(current_user["id"])
    conn = await onairos_service.get_connection(user_id, db)
    if conn is None or conn.revoked_at is not None:
        return OnairosStatusResponse(connected=False)
    return OnairosStatusResponse(
        connected=True,
        connected_at=_iso(conn.connected_at),
        token_expires_at=_iso(conn.token_expires_at),
        traits_cached_at=_iso(conn.traits_cached_at),
        approved_requests=conn.approved_requests or {},
        traits=conn.traits_cached,
    )


@router.delete("/disconnect")
async def disconnect(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Revoke the user's Onairos connection; coaching stops using the trait slot."""
    user_id = str(current_user["id"])
    removed = await onairos_service.mark_revoked(user_id, db)
    try:
        from services.coaching_service import coaching_service
        coaching_service.invalidate_context_cache(user_id)
    except Exception:
        pass
    return {"ok": True, "removed": removed}
