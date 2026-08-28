"""
Google integrations (Calendar / Gmail / Maps Platform) feeding the planner.

Design rules:
  - Everything is CONFIG-GATED: with no keys, every function is a graceful
    no-op and the API reports {available: false}. The algorithm never
    depends on Google being present - it gets richer when it is.
  - Calendar events land in the SAME calendar_events table the device path
    uses, so the merge / today-read / feasibility logic is identical no
    matter where a busy block came from.
  - Gmail findings are PROPOSALS (status='proposed', is_busy=False). They
    never touch the plan until the user confirms - confirm-first, like
    every other inference (spec P2). Raw email content never reaches an
    LLM; we extract structured {title, starts_at, ends_at} and drop the rest.
  - Maps gives two things: place resolution (typed address -> lat/lng) and
    commute minutes (Distance Matrix) for the leave-by hint. Both cached,
    both with time-based fallbacks.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.sqlalchemy_models import (
    CalendarConnection,
    CalendarEvent,
    User,
    UserPlace,
)

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
GMAIL_LIST_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
GMAIL_GET_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}"
PLACES_TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

SCOPE_CALENDAR = "https://www.googleapis.com/auth/calendar.readonly"
SCOPE_GMAIL = "https://www.googleapis.com/auth/gmail.readonly"
# Write access to calendars THIS APP CREATED — never the user's own.
# Narrower than calendar.events (which grants write on `primary`), so a bug
# in the mirror can only ever damage the "Max" calendar we made.
SCOPE_CALENDAR_APP = "https://www.googleapis.com/auth/calendar.app.created"

SYNC_WINDOW_DAYS = 60   # ~2 months; re-sync nudge fires when < RESYNC_NUDGE_DAYS remain
RESYNC_NUDGE_DAYS = 7   # /status returns needs_resync=True when coverage drops below this

# Google's OpenID Connect endpoints for verifying Sign-In ID tokens.
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


def google_oauth_available() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri)


def maps_available() -> bool:
    return bool(settings.google_maps_api_key)


# --- Google Sign-In (identity) ID-token verification -----------------------

def google_signin_client_ids() -> list[str]:
    """Every client id an ID token's `aud` may legitimately carry: the
    per-platform Sign-In clients plus the base OAuth client."""
    ids = [
        settings.google_web_client_id,
        settings.google_ios_client_id,
        settings.google_client_id,
    ]
    return [c for c in dict.fromkeys(ids) if c]


def google_signin_available() -> bool:
    return bool(google_signin_client_ids())


_jwks_client = None  # lazily built; PyJWKClient caches keys internally


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        from jwt import PyJWKClient
        _jwks_client = PyJWKClient(GOOGLE_JWKS_URL)
    return _jwks_client


def _verify_google_id_token_sync(token: str) -> dict:
    """Verify a Google ID token locally (RS256 against Google's JWKS) and
    return its claims. Raises ValueError on any failure. Synchronous - the
    async wrapper runs it off the event loop."""
    import jwt as pyjwt  # PyJWT, distinct from the python-jose `jwt` in auth.py

    audiences = google_signin_client_ids()
    if not audiences:
        raise ValueError("Google Sign-In is not configured")
    signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
    claims = pyjwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audiences,
        options={"require": ["exp", "iss", "sub", "aud"]},
    )
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise ValueError("Bad token issuer")
    return claims


async def verify_google_id_token(token: str) -> dict:
    """Async verify. Returns the validated claims dict (sub, email,
    email_verified, given_name, family_name, picture, ...)."""
    import asyncio

    if not token or not isinstance(token, str):
        raise ValueError("Missing token")
    try:
        return await asyncio.to_thread(_verify_google_id_token_sync, token)
    except ValueError:
        raise
    except Exception as e:  # jwt errors, network, key lookup
        raise ValueError(f"Invalid Google token: {e}") from e


def gmail_scan_available() -> bool:
    return google_oauth_available() and bool(settings.gmail_scan_enabled)


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------

def build_auth_url(state: str, include_gmail: bool, include_write: bool = False) -> str:
    scopes = [SCOPE_CALENDAR]
    if include_gmail and gmail_scan_available():
        scopes.append(SCOPE_GMAIL)
    if include_write and getattr(settings, "gcal_write_enabled", False):
        scopes.append(SCOPE_CALENDAR_APP)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.google_redirect_uri,
        })
        resp.raise_for_status()
        return resp.json()


async def _fresh_access_token(conn: CalendarConnection, db: AsyncSession) -> str | None:
    """Refresh-token dance; updates stored expiry. None = needs reconnect."""
    from services.secrets import encrypt_token
    import json
    tokens = conn.tokens_decrypted  # dual-read: encrypted first, fallback plaintext
    access = tokens.get("access_token")
    expiry = tokens.get("expiry")
    if access and expiry:
        try:
            if datetime.fromisoformat(str(expiry)) > datetime.utcnow() + timedelta(minutes=2):
                return str(access)
        except ValueError:
            pass
    refresh = tokens.get("refresh_token")
    if not refresh:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.warning("google token refresh failed: %s", e)
        return None
    tokens["access_token"] = data.get("access_token")
    tokens["expiry"] = (
        datetime.utcnow() + timedelta(seconds=int(data.get("expires_in") or 3600))
    ).isoformat()
    conn.tokens_encrypted = encrypt_token(json.dumps(tokens))
    conn.tokens = None
    await db.commit()
    return tokens.get("access_token")


async def store_connection(
    db: AsyncSession, user_id, token_payload: dict[str, Any]
) -> CalendarConnection:
    conn = (await db.execute(
        select(CalendarConnection).where(
            (CalendarConnection.user_id == user_id)
            & (CalendarConnection.provider == "google")
        )
    )).scalars().first()
    if conn is None:
        conn = CalendarConnection(user_id=user_id, provider="google")
        db.add(conn)
    import json
    from services.secrets import encrypt_token
    tokens = conn.tokens_decrypted  # dual-read: encrypted first, fallback plaintext
    tokens["access_token"] = token_payload.get("access_token")
    if token_payload.get("refresh_token"):
        tokens["refresh_token"] = token_payload["refresh_token"]
    tokens["scope"] = token_payload.get("scope", "")
    tokens["expiry"] = (
        datetime.utcnow() + timedelta(seconds=int(token_payload.get("expires_in") or 3600))
    ).isoformat()
    conn.tokens_encrypted = encrypt_token(json.dumps(tokens))
    conn.tokens = None  # clear plaintext after encrypting
    conn.is_active = True
    await db.commit()
    return conn


# ---------------------------------------------------------------------------
# Calendar sync
# ---------------------------------------------------------------------------

def _parse_gcal_time(node: dict) -> datetime | None:
    """Google gives either dateTime (offset-aware) or date (all-day). We keep
    the WALL-CLOCK convention used everywhere: drop the offset, tag as UTC."""
    raw = node.get("dateTime") or node.get("date")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc)


async def sync_google_calendar(user_id, db: AsyncSession) -> dict[str, int]:
    """Pull the next SYNC_WINDOW_DAYS of events into calendar_events with
    window-replace semantics (deletions on Google propagate)."""
    conn = (await db.execute(
        select(CalendarConnection).where(
            (CalendarConnection.user_id == user_id)
            & (CalendarConnection.provider == "google")
            & (CalendarConnection.is_active.is_(True))
        )
    )).scalars().first()
    if conn is None:
        return {"synced": 0}
    access = await _fresh_access_token(conn, db)
    if not access:
        # Refresh failed → mark connection inactive so the UI shows reconnect state
        conn.is_active = False
        await db.commit()
        return {"synced": 0, "needs_reconnect": 1}

    win_from = datetime.utcnow() - timedelta(days=1)
    win_to = datetime.utcnow() + timedelta(days=SYNC_WINDOW_DAYS)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                CALENDAR_EVENTS_URL,
                params={
                    "timeMin": win_from.replace(tzinfo=timezone.utc).isoformat(),
                    "timeMax": win_to.replace(tzinfo=timezone.utc).isoformat(),
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "maxResults": 250,
                },
                headers={"Authorization": f"Bearer {access}"},
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
    except httpx.HTTPError as e:
        logger.warning("google calendar sync failed for %s: %s", user_id, e)
        return {"synced": 0, "error": 1}

    await db.execute(
        delete(CalendarEvent).where(
            (CalendarEvent.user_id == user_id)
            & (CalendarEvent.connection_id == conn.id)
            & (CalendarEvent.starts_at >= win_from.replace(tzinfo=timezone.utc))
            & (CalendarEvent.starts_at < win_to.replace(tzinfo=timezone.utc))
        )
    )

    synced = 0
    fresh_rows: list[dict] = []
    for ev in items:
        if ev.get("status") == "cancelled":
            continue
        # Never re-ingest the routine WE wrote. Today this can't happen (we read
        # only `primary`, we write to a dedicated calendar), but if the read ever
        # widens, ingesting our own tasks as busy time would make the plan
        # collide with itself and shrink on every regeneration.
        if ((ev.get("extendedProperties") or {}).get("private") or {}).get("maxapp"):
            continue
        starts = _parse_gcal_time(ev.get("start") or {})
        ends = _parse_gcal_time(ev.get("end") or {})
        if not starts or not ends:
            continue
        transparency = ev.get("transparency") or "opaque"  # opaque = busy
        db.add(CalendarEvent(
            user_id=user_id,
            connection_id=conn.id,
            external_event_id=str(ev.get("id") or "")[:255] or None,
            title=(str(ev.get("summary") or "")[:255] or None),
            starts_at=starts,
            ends_at=ends,
            all_day="date" in (ev.get("start") or {}),
            location=(str(ev.get("location") or "")[:255] or None),
            is_busy=(transparency == "opaque"),
            status="confirmed",
        ))
        synced += 1
        fresh_rows.append({
            "starts_at": starts, "ends_at": ends,
            "status": "confirmed", "is_busy": (transparency == "opaque"),
            "all_day": "date" in (ev.get("start") or {}),
            "external_event_id": str(ev.get("id") or ""), "raw": {},
        })
    conn.last_synced_at = datetime.utcnow()
    await db.commit()

    # Did their real commitments actually MOVE? This runs every 30 minutes and
    # again on every app foreground, so a plain "we synced" trigger would
    # regenerate plans constantly. Fingerprinting only the events that can
    # displace a task means an unchanged calendar costs nothing.
    try:
        await _maybe_regen_on_calendar_drift(user_id, fresh_rows, db)
    except Exception as e:
        logger.warning("calendar drift check failed for %s: %s", user_id, e)

    return {"synced": synced}


_DRIFT_DEBOUNCE_MINUTES = 15


async def _maybe_regen_on_calendar_drift(user_id, rows: list[dict], db) -> None:
    """Reflow active plans when the user's real calendar has changed shape."""
    from sqlalchemy.orm.attributes import flag_modified

    from models.sqlalchemy_models import User, UserSchedule
    from services.calendar_busy import busy_fingerprint

    user = await db.get(User, user_id)
    if user is None:
        return
    prof = dict(user.profile or {})
    fp = busy_fingerprint(rows)
    if prof.get("gcal_busy_fp") == fp:
        return  # calendar unchanged — nothing to do

    now = datetime.utcnow()
    last = prof.get("gcal_drift_regen_at")
    if last:
        try:
            if (now - datetime.fromisoformat(last)).total_seconds() < _DRIFT_DEBOUNCE_MINUTES * 60:
                return
        except Exception:
            pass

    has_active = (await db.execute(
        select(UserSchedule.id).where(
            (UserSchedule.user_id == user_id) & (UserSchedule.is_active.is_(True))
        ).limit(1)
    )).first() is not None

    prof["gcal_busy_fp"] = fp
    if has_active:
        prof["gcal_drift_regen_at"] = now.isoformat()
    user.profile = prof
    flag_modified(user, "profile")
    await db.commit()

    if not has_active:
        return
    from services.schedule_runtime import regenerate_active_schedules
    await regenerate_active_schedules(user_id=str(user_id), db=db, reason="calendar_drift")
    await db.commit()


# ---------------------------------------------------------------------------
# Maps: place resolution + commute minutes
# ---------------------------------------------------------------------------

async def resolve_place(place: UserPlace, db: AsyncSession) -> bool:
    """Typed address/name -> place_id + lat/lng. No-op without a key."""
    if not maps_available():
        return False
    query = place.address or place.name
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(PLACES_TEXTSEARCH_URL, params={
                "query": query,
                "key": settings.google_maps_api_key,
            })
            resp.raise_for_status()
            results = resp.json().get("results", [])
    except httpx.HTTPError as e:
        logger.warning("places resolve failed: %s", e)
        return False
    if not results:
        return False
    top = results[0]
    place.google_place_id = top.get("place_id")
    loc = ((top.get("geometry") or {}).get("location") or {})
    place.lat = loc.get("lat")
    place.lng = loc.get("lng")
    if top.get("formatted_address"):
        place.address = str(top["formatted_address"])[:255]
    await db.commit()
    return True


# Tiny in-process cache: (origin_id, dest_id) -> (minutes, computed_at)
_commute_cache: dict[tuple[str, str], tuple[int, datetime]] = {}
_COMMUTE_TTL = timedelta(hours=6)
FALLBACK_COMMUTE_MIN = 25  # honest time-based fallback (spec 4.8)


async def commute_minutes(origin: UserPlace, dest: UserPlace) -> int:
    """Driving minutes between two resolved places. Cached; falls back to a
    flat estimate when Maps is unavailable - the leave-by copy must tolerate
    this ('give yourself ~25 minutes')."""
    if not (origin.lat and origin.lng and dest.lat and dest.lng):
        return FALLBACK_COMMUTE_MIN
    key = (str(origin.id), str(dest.id))
    cached = _commute_cache.get(key)
    if cached and datetime.utcnow() - cached[1] < _COMMUTE_TTL:
        return cached[0]
    if not maps_available():
        return FALLBACK_COMMUTE_MIN
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(DISTANCE_MATRIX_URL, params={
                "origins": f"{origin.lat},{origin.lng}",
                "destinations": f"{dest.lat},{dest.lng}",
                "mode": "driving",
                "key": settings.google_maps_api_key,
            })
            resp.raise_for_status()
            rows = resp.json().get("rows", [])
        seconds = rows[0]["elements"][0]["duration"]["value"]
        minutes = max(1, int(seconds // 60))
    except (httpx.HTTPError, LookupError, KeyError, TypeError) as e:
        logger.warning("distance matrix failed: %s", e)
        return FALLBACK_COMMUTE_MIN
    _commute_cache[key] = (minutes, datetime.utcnow())
    return minutes


# ---------------------------------------------------------------------------
# Gmail commitment scan (confirm-first proposals)
# ---------------------------------------------------------------------------

_COMMITMENT_QUERY = (
    "subject:(reservation OR appointment OR confirmation OR booking OR flight "
    "OR itinerary OR invite) newer_than:14d -category:promotions"
)

# Conservative datetime extraction from subjects/snippets. We only propose
# when we find an explicit date AND time; anything fuzzier is skipped.
_DT_PATTERNS = [
    # "June 14 at 2:30 PM" / "Jun 14, 2:30pm"
    re.compile(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:,?\s*(?:at\s+)?|\s+at\s+)(\d{1,2}):(\d{2})\s*([AaPp])\.?[Mm]?",
    ),
    # "6/14 2:30 PM"
    re.compile(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})\s*([AaPp])\.?[Mm]?"),
]
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
)}


def extract_commitment_datetime(text: str, *, now: datetime) -> datetime | None:
    """First explicit future date+time in the text, else None. Pure; tested."""
    for pat in _DT_PATTERNS:
        m = pat.search(text or "")
        if not m:
            continue
        g = m.groups()
        try:
            if g[0] in _MONTHS or (g[0] or "").capitalize() in _MONTHS:
                month = _MONTHS[(g[0]).capitalize()]
                day, hour, minute = int(g[1]), int(g[2]), int(g[3])
                ampm = g[4].lower()
            else:
                month, day, hour, minute = int(g[0]), int(g[1]), int(g[2]), int(g[3])
                ampm = g[4].lower()
            if ampm == "p" and hour != 12:
                hour += 12
            if ampm == "a" and hour == 12:
                hour = 0
            year = now.year
            candidate = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
            if candidate < now.replace(tzinfo=timezone.utc) - timedelta(days=1):
                candidate = candidate.replace(year=year + 1)
            return candidate
        except (ValueError, KeyError):
            continue
    return None


async def scan_gmail_commitments(user_id, db: AsyncSession) -> dict[str, int]:
    """Find schedule-relevant emails and store PROPOSED busy blocks. The user
    confirms each one before it touches the plan. Subjects only - bodies are
    never fetched, nothing reaches an LLM."""
    if not gmail_scan_available():
        return {"proposed": 0, "available": 0}
    conn = (await db.execute(
        select(CalendarConnection).where(
            (CalendarConnection.user_id == user_id)
            & (CalendarConnection.provider == "google")
            & (CalendarConnection.is_active.is_(True))
        )
    )).scalars().first()
    # Read the DECRYPTED tokens — conn.tokens (plaintext) is set to None after
    # Fernet-encrypting into tokens_encrypted, so the old `conn.tokens` read was
    # always {} and the Gmail scope gate always failed (Gmail scan never ran).
    if conn is None or SCOPE_GMAIL not in str((conn.tokens_decrypted or {}).get("scope") or ""):
        return {"proposed": 0, "needs_scope": 1}
    access = await _fresh_access_token(conn, db)
    if not access:
        return {"proposed": 0, "needs_reconnect": 1}

    headers = {"Authorization": f"Bearer {access}"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(GMAIL_LIST_URL, params={
                "q": _COMMITMENT_QUERY, "maxResults": 20,
            }, headers=headers)
            resp.raise_for_status()
            ids = [m["id"] for m in resp.json().get("messages", [])]

            proposed = 0
            now = datetime.utcnow()
            for mid in ids[:20]:
                mresp = await client.get(
                    GMAIL_GET_URL.format(id=mid),
                    params={"format": "metadata", "metadataHeaders": "Subject"},
                    headers=headers,
                )
                if mresp.status_code != 200:
                    continue
                data = mresp.json()
                subject = next(
                    (h["value"] for h in (data.get("payload") or {}).get("headers", [])
                     if h.get("name") == "Subject"),
                    "",
                )
                snippet = str(data.get("snippet") or "")
                when = extract_commitment_datetime(f"{subject} {snippet}", now=now)
                if when is None:
                    continue
                # Dedup on external id.
                existing = (await db.execute(
                    select(CalendarEvent).where(
                        (CalendarEvent.user_id == user_id)
                        & (CalendarEvent.external_event_id == f"gmail:{mid}")
                    )
                )).scalars().first()
                if existing:
                    continue
                db.add(CalendarEvent(
                    user_id=user_id,
                    connection_id=conn.id,
                    external_event_id=f"gmail:{mid}",
                    title=(subject or "Found in Gmail")[:255],
                    starts_at=when,
                    ends_at=when + timedelta(hours=1),
                    is_busy=False,           # not busy until confirmed
                    status="proposed",       # confirm-first
                ))
                proposed += 1
            await db.commit()
            return {"proposed": proposed}
    except httpx.HTTPError as e:
        logger.warning("gmail scan failed for %s: %s", user_id, e)
        return {"proposed": 0, "error": 1}
