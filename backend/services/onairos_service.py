"""Onairos personalization service.

The mobile app runs the Onairos consent UI via `@onairos/react-native` and
receives `{apiUrl, accessToken, approvedRequests, userData?}` from the SDK's
`onResolved` callback. The mobile client POSTs that payload to
`POST /api/onairos/connect`, which lands here.

All inference calls use the per-user `apiUrl + accessToken` returned by the
SDK. There is no global Onairos API key on the backend — tokens are
user-scoped and rotate on re-consent.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from config import settings
from models.sqlalchemy_models import UserOnairosConnection

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _decode_jwt_exp(token: str) -> Optional[datetime]:
    """Best-effort parse of a JWT `exp` claim without signature verification.

    We only use this to populate token_expires_at for UX ("reconnect required
    after X"). It is not a security boundary — Onairos verifies its own token.
    """
    try:
        import base64

        parts = token.split(".")
        if len(parts) < 2:
            return None
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        exp = payload.get("exp")
        if isinstance(exp, (int, float)):
            return datetime.fromtimestamp(float(exp), tz=timezone.utc)
    except Exception:
        return None
    return None


class OnairosService:
    """Persistence + API calls for per-user Onairos connections."""

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def get_connection(
        self, user_id: str, db: AsyncSession
    ) -> Optional[UserOnairosConnection]:
        result = await db.execute(
            select(UserOnairosConnection).where(
                UserOnairosConnection.user_id == UUID(user_id)
            )
        )
        return result.scalar_one_or_none()

    async def get_active_traits(
        self, user_id: str, db: AsyncSession
    ) -> Optional[dict[str, Any]]:
        """Return cached trait snapshot if the user has an active (non-revoked)
        connection. The coaching context builder calls this — it never triggers
        a network request itself."""
        conn = await self.get_connection(user_id, db)
        if not conn or conn.revoked_at is not None:
            return None
        return conn.traits_cached or None

    async def save_handoff(
        self,
        user_id: str,
        db: AsyncSession,
        *,
        api_url: str,
        access_token: str,
        approved_requests: Optional[dict[str, Any]] = None,
        user_basic: Optional[dict[str, Any]] = None,
    ) -> UserOnairosConnection:
        """Persist the SDK handoff. Upserts on user_id."""
        conn = await self.get_connection(user_id, db)
        now = _utcnow()
        expires_at = _decode_jwt_exp(access_token)
        if conn is None:
            conn = UserOnairosConnection(
                user_id=UUID(user_id),
                api_url=api_url,
                access_token=access_token,
                token_expires_at=expires_at,
                approved_requests=approved_requests or {},
                user_basic=user_basic,
                connected_at=now,
            )
            db.add(conn)
        else:
            conn.api_url = api_url
            conn.access_token = access_token
            conn.token_expires_at = expires_at
            conn.approved_requests = approved_requests or {}
            if user_basic is not None:
                conn.user_basic = user_basic
            conn.connected_at = now
            conn.revoked_at = None
            flag_modified(conn, "approved_requests")
            if user_basic is not None:
                flag_modified(conn, "user_basic")
        await db.commit()
        await db.refresh(conn)
        return conn

    async def mark_revoked(self, user_id: str, db: AsyncSession) -> bool:
        conn = await self.get_connection(user_id, db)
        if conn is None:
            return False
        conn.revoked_at = _utcnow()
        conn.traits_cached = None
        conn.traits_cached_at = None
        await db.commit()
        return True

    # ------------------------------------------------------------------
    # Onairos API — per-user token calls
    # ------------------------------------------------------------------

    async def _post_inference(
        self, *, api_url: str, access_token: str, payload: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        timeout = float(getattr(settings, "onairos_http_timeout_seconds", 6.0) or 6.0)
        body = {**payload, "accessToken": access_token}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    api_url,
                    json=body,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "onairos inference failed status=%s body=%.200s",
                e.response.status_code,
                e.response.text,
            )
        except Exception as e:
            logger.warning("onairos inference exception: %s", e)
        return None

    async def refresh_traits(
        self,
        user_id: str,
        db: AsyncSession,
        *,
        seed_text: str = "wellness lifestyle grooming skincare fitness",
    ) -> Optional[dict[str, Any]]:
        """Pull the latest trait/sentiment snapshot for this user and cache it.

        `seed_text` is an anchor input that nudges Onairos toward the maxapp
        domain. Callers can override it per use case (e.g. a scan turn may
        want "skin routine acne").
        """
        conn = await self.get_connection(user_id, db)
        if conn is None or conn.revoked_at is not None:
            return None

        result = await self._post_inference(
            api_url=conn.api_url,
            access_token=conn.access_token,
            payload={
                "inputData": [
                    {"text": seed_text, "category": "wellness"},
                ],
            },
        )
        if not isinstance(result, dict):
            return None

        traits = {
            "traits": result.get("Traits") or {},
            "inference": result.get("InferenceResult") or {},
        }
        conn.traits_cached = traits
        conn.traits_cached_at = _utcnow()
        flag_modified(conn, "traits_cached")
        await db.commit()
        return traits

    # ------------------------------------------------------------------
    # Memory-slot formatting — read-only, safe to call from coaching
    # ------------------------------------------------------------------

    @staticmethod
    def format_traits_slot(traits_cached: dict[str, Any] | None) -> Optional[str]:
        """Render the cached trait snapshot into a single MEMORY SLOT line.
        Returns None when there is nothing worth showing."""
        if not traits_cached:
            return None
        traits_obj = traits_cached.get("traits") or {}
        positive = traits_obj.get("positive_traits") or {}
        to_improve = traits_obj.get("traits_to_improve") or {}

        def _top(d: dict[str, Any], n: int = 3) -> list[str]:
            numeric: list[tuple[str, float]] = []
            for name, score in d.items():
                if not name:
                    continue
                try:
                    numeric.append((str(name), float(score)))
                except (TypeError, ValueError):
                    continue
            numeric.sort(key=lambda kv: kv[1], reverse=True)
            return [f"{name} ({score:.1f})" for name, score in numeric[:n]]

        pos = _top(positive, 3)
        neg = _top(to_improve, 2)
        if not pos and not neg:
            return None
        parts = []
        if pos:
            parts.append("strengths: " + ", ".join(pos))
        if neg:
            parts.append("room to grow: " + ", ".join(neg))
        return "- traits (onairos): " + " | ".join(parts)


onairos_service = OnairosService()
