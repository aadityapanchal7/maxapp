"""Raw httpx client for WRITING to Google Calendar.

The repo talks to Google with plain httpx and hand-built requests (see
`google_integration`), no SDK — this follows that. Everything here is transport:
build a request, send it, parse the reply. All the "what should the calendar
look like" logic lives in `gcal_mirror`.

Scope note: every call here targets a calendar THIS APP CREATED
(`calendar.app.created`). We can never touch the user's own events, so a bug in
the reconcile can lose Max's mirror but not the user's real calendar.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
BATCH_URL = "https://www.googleapis.com/batch/calendar/v3"

# Google's documented ceiling for a batch request.
BATCH_MAX_OPS = 50
_HTTP_TIMEOUT = 30.0
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)

MAX_CALENDAR_SUMMARY = "Max"
_MANAGED_NOTE = (
    "Managed by Max — this updates automatically when your routine changes."
)


class GcalRateLimited(RuntimeError):
    """Google asked us to slow down and we exhausted our backoff."""


class GcalAuthExpired(RuntimeError):
    """Access token rejected — the caller should mark the connection stale."""


# --------------------------------------------------------------------------- #
#  Calendar lifecycle                                                          #
# --------------------------------------------------------------------------- #

async def create_calendar(access_token: str, *, tz_name: str,
                          summary: str = MAX_CALENDAR_SUMMARY) -> str | None:
    """Create the dedicated Max calendar; returns its id."""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.post(
            f"{CALENDAR_BASE}/calendars",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"summary": summary, "timeZone": tz_name,
                  "description": "Your Max routine. " + _MANAGED_NOTE},
        )
    if r.status_code == 401:
        raise GcalAuthExpired("create_calendar got 401")
    if r.status_code >= 400:
        logger.warning("create_calendar failed %s: %s", r.status_code, r.text[:200])
        return None
    return (r.json() or {}).get("id")


async def delete_calendar(access_token: str, calendar_id: str) -> bool:
    """Remove the Max calendar entirely. Already-gone counts as success."""
    if not calendar_id:
        return True
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.delete(
            f"{CALENDAR_BASE}/calendars/{calendar_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    return r.status_code in (200, 204, 404, 410)


# --------------------------------------------------------------------------- #
#  Event bodies                                                                #
# --------------------------------------------------------------------------- #

def event_body(
    *,
    event_id: str,
    title: str,
    start_local: str,
    end_local: str,
    tz_name: str,
    event_key: str,
    description: str = "",
) -> dict:
    """A Google event for one Max task.

    Times are sent as naive local wall-clock plus an explicit IANA `timeZone`,
    never as UTC instants — that is the convention the whole schedule uses, and
    it means an event stays at 07:30 for the user across a DST boundary.

    `reminders` is explicitly emptied: the app already sends its own push for
    every task, and inheriting Google's defaults would double-notify.
    """
    body: dict = {
        "summary": title,
        "start": {"dateTime": start_local, "timeZone": tz_name},
        "end": {"dateTime": end_local, "timeZone": tz_name},
        "reminders": {"useDefault": False, "overrides": []},
        "extendedProperties": {"private": {"maxapp": "1", "event_key": event_key}},
        "description": (description + "\n\n" if description else "") + _MANAGED_NOTE,
    }
    if event_id:
        body["id"] = event_id
    return body


# --------------------------------------------------------------------------- #
#  Batch execution                                                             #
# --------------------------------------------------------------------------- #

@dataclass
class BatchOp:
    method: str          # "POST" | "PATCH" | "PUT" | "DELETE"
    path: str            # e.g. "/calendar/v3/calendars/{cal}/events"
    body: dict | None
    ref: str             # our correlation id (the event key hex)


_BOUNDARY = "maxapp-gcal-batch"


def _encode_batch(ops: list[BatchOp]) -> str:
    parts: list[str] = []
    for op in ops:
        lines = [
            f"--{_BOUNDARY}",
            "Content-Type: application/http",
            f"Content-ID: <{op.ref}>",
            "",
            f"{op.method} {op.path}",
        ]
        if op.body is not None:
            payload = json.dumps(op.body)
            lines += ["Content-Type: application/json",
                      f"Content-Length: {len(payload)}", "", payload]
        else:
            lines += [""]
        parts.append("\r\n".join(lines))
    return "\r\n".join(parts) + f"\r\n--{_BOUNDARY}--\r\n"


_CONTENT_ID_RE = re.compile(r"Content-ID:\s*<response-([^>]+)>", re.I)
_STATUS_RE = re.compile(r"HTTP/[\d.]+\s+(\d{3})")


def _parse_batch(raw: str) -> dict[str, tuple[int, dict]]:
    """Map our Content-ID refs back to (status, parsed body).

    Google echoes each request's Content-ID prefixed with "response-".
    """
    out: dict[str, tuple[int, dict]] = {}
    # Split on the multipart boundary Google chose (it echoes its own).
    chunks = re.split(r"--batch[_A-Za-z0-9-]*", raw) or []
    if len(chunks) <= 1:
        chunks = re.split(rf"--{_BOUNDARY}", raw)
    for chunk in chunks:
        m_id = _CONTENT_ID_RE.search(chunk)
        m_st = _STATUS_RE.search(chunk)
        if not m_id or not m_st:
            continue
        ref = m_id.group(1).strip()
        status = int(m_st.group(1))
        body: dict = {}
        brace = chunk.find("{")
        if brace != -1:
            try:
                body = json.loads(chunk[brace:chunk.rfind("}") + 1])
            except Exception:
                body = {}
        out[ref] = (status, body)
    return out


async def execute_batch(access_token: str, ops: list[BatchOp]) -> dict[str, tuple[int, dict]]:
    """Run ops in chunks of BATCH_MAX_OPS; return {ref: (status, body)}.

    Rate limits get a bounded retry — Google's 403/429 for a busy account is
    transient, and the 30-minute reconcile job will pick up anything we abandon.
    """
    results: dict[str, tuple[int, dict]] = {}
    if not ops:
        return results

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for i in range(0, len(ops), BATCH_MAX_OPS):
            chunk = ops[i:i + BATCH_MAX_OPS]
            payload = _encode_batch(chunk)
            for attempt in range(len(_BACKOFF_SECONDS) + 1):
                r = await client.post(
                    BATCH_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": f"multipart/mixed; boundary={_BOUNDARY}",
                    },
                    content=payload,
                )
                if r.status_code == 401:
                    raise GcalAuthExpired("batch got 401")
                if r.status_code in (403, 429) and attempt < len(_BACKOFF_SECONDS):
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                    continue
                if r.status_code in (403, 429):
                    raise GcalRateLimited(f"batch rate limited after {attempt + 1} tries")
                break
            if r.status_code >= 400:
                logger.warning("gcal batch chunk failed %s: %s", r.status_code, r.text[:200])
                continue
            results.update(_parse_batch(r.text))
    return results
