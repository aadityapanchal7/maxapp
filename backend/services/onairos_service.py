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
    def _top(d: dict[str, Any], n: int = 3) -> list[tuple[str, float]]:
        numeric: list[tuple[str, float]] = []
        for name, score in (d or {}).items():
            if not name:
                continue
            try:
                numeric.append((str(name), float(score)))
            except (TypeError, ValueError):
                continue
        numeric.sort(key=lambda kv: kv[1], reverse=True)
        return numeric[:n]

    @staticmethod
    def format_traits_slot(traits_cached: dict[str, Any] | None) -> Optional[str]:
        """Render the cached trait snapshot into a single MEMORY SLOT line.
        Returns None when there is nothing worth showing."""
        if not traits_cached:
            return None
        traits_obj = traits_cached.get("traits") or {}
        positive = traits_obj.get("positive_traits") or {}
        to_improve = traits_obj.get("traits_to_improve") or {}
        inference = traits_cached.get("inference") or {}

        def _fmt(pairs: list[tuple[str, float]]) -> list[str]:
            return [f"{name} ({score:.1f})" for name, score in pairs]

        pos = _fmt(OnairosService._top(positive, 3))
        neg = _fmt(OnairosService._top(to_improve, 2))

        parts = []
        if pos:
            parts.append("strengths: " + ", ".join(pos))
        if neg:
            parts.append("room to grow: " + ", ".join(neg))

        # Surface top inference affinities so Agartha can tailor tone / topic (e.g. more or
        # less fitness-heavy framing) when the chat prompt says to quietly personalize.
        affinities_raw = inference.get("affinities") or inference.get("interests") or {}
        if isinstance(affinities_raw, dict) and affinities_raw:
            aff_top = _fmt(OnairosService._top(affinities_raw, 3))
            if aff_top:
                parts.append("affinities: " + ", ".join(aff_top))

        if not parts:
            return None
        return "- traits (onairos): " + " | ".join(parts)

    # --- deterministic trait → behavioral-frame sentences -------------------
    #
    # Keep narrow and literal. Each key matches the lowercased trait name from
    # Onairos; the value is a one-line framing directive Agartha can lean on. We
    # never cite the source and never list scores — the frame reads as Agartha's
    # own observation about the user.
    _STRENGTH_FRAMES: dict[str, str] = {
        "consistency": "Rides habit well — frame protocols as streaks, not novel stacks.",
        "discipline": "High discipline — can handle stricter targets than average.",
        "openness": "Open to trying new protocols; willing to experiment.",
        "conscientiousness": "Detail-oriented — give exact numbers, not vague ranges.",
        "extraversion": "Responds to accountability framing (public streaks, check-ins).",
    }
    _IMPROVE_FRAMES: dict[str, str] = {
        "consistency": "Tends to start strong and fade by week 2. Frame in 7-day blocks, not 30-day arcs.",
        "discipline": "Discipline-rebuild mode — pick 2-3 core actions, not a full stack.",
        "neuroticism": "Don't pile on — one action per reply, skip scolding tone even in candid mode.",
        "openness": "Low novelty tolerance — stick to core protocol; don't suggest experiments.",
        "agreeableness": "Won't push back easily — double-check they're actually on board before ratcheting intensity.",
    }

    @staticmethod
    def format_behavioral_frame(traits_cached: dict[str, Any] | None) -> Optional[str]:
        """Return a short multi-line frame Agartha can treat as facts-about-the-user.

        Output is already labelled — callers append it directly to context.
        Never names the source. Never lists numeric scores. Returns None when
        there is nothing high-signal enough to frame.
        """
        if not traits_cached:
            return None
        traits_obj = traits_cached.get("traits") or {}
        positive = traits_obj.get("positive_traits") or {}
        to_improve = traits_obj.get("traits_to_improve") or {}

        lines: list[str] = []
        for name, score in OnairosService._top(positive, 2):
            key = name.strip().lower()
            if score < 0.55:
                continue
            frame = OnairosService._STRENGTH_FRAMES.get(key)
            if frame:
                lines.append(f"- {frame}")
        for name, score in OnairosService._top(to_improve, 2):
            key = name.strip().lower()
            if score < 0.55:
                continue
            frame = OnairosService._IMPROVE_FRAMES.get(key)
            if frame:
                lines.append(f"- {frame}")

        # Dedupe while preserving order (traits may collide across buckets).
        seen: set[str] = set()
        unique: list[str] = []
        for ln in lines:
            if ln in seen:
                continue
            seen.add(ln)
            unique.append(ln)

        if not unique:
            return None
        return "## USER BEHAVIORAL FRAME (internal — never cite source, never name it)\n" + "\n".join(unique)

    @staticmethod
    def query_bias_terms(traits_cached: dict[str, Any] | None) -> Optional[str]:
        """Return a short space-joined string of bias terms to append to a RAG query.

        Biases retrieval toward docs that match the user's behavioral profile
        (e.g. "habit-stacking" sections for low-consistency users). Narrow on
        purpose — too many terms drown the signal from the actual question.
        """
        if not traits_cached:
            return None
        traits_obj = traits_cached.get("traits") or {}
        improve = traits_obj.get("traits_to_improve") or {}

        TERM_MAP: dict[str, str] = {
            "consistency": "habit stacking beginner routine",
            "discipline": "minimal effective dose beginner",
            "openness": "standard protocol core stack",
            "neuroticism": "gentle low-intensity starter",
        }
        terms: list[str] = []
        for name, score in OnairosService._top(improve, 2):
            if score < 0.55:
                continue
            m = TERM_MAP.get(name.strip().lower())
            if m:
                terms.append(m)
        if not terms:
            return None
        # Dedupe individual tokens.
        tokens = list(dict.fromkeys(" ".join(terms).split()))
        return " ".join(tokens)


onairos_service = OnairosService()
