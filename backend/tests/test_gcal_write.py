"""Google Calendar write transport: batching, parsing, and failure handling.

Every Google call is monkeypatched — nothing here touches the network.
"""

import pytest

from services.gcal_write import (
    BATCH_MAX_OPS,
    BatchOp,
    GcalAuthExpired,
    GcalRateLimited,
    _encode_batch,
    _parse_batch,
    event_body,
    execute_batch,
)


class FakeResponse:
    def __init__(self, status_code=200, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeClient:
    """Stands in for httpx.AsyncClient; records what we would have sent."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, content=None, json=None, params=None):
        self.calls.append({"url": url, "content": content, "json": json})
        return self._responses.pop(0) if self._responses else FakeResponse(200, "")

    async def delete(self, url, headers=None):
        self.calls.append({"url": url, "method": "DELETE"})
        return self._responses.pop(0) if self._responses else FakeResponse(204, "")


def _install(monkeypatch, client):
    import services.gcal_write as gw
    monkeypatch.setattr(gw.httpx, "AsyncClient", lambda **kw: client)
    return client


def _batch_response(entries):
    """Build a multipart body shaped like Google's batch reply."""
    parts = []
    for ref, status, body in entries:
        parts.append(
            f"--batch_abc123\r\n"
            f"Content-Type: application/http\r\n"
            f"Content-ID: <response-{ref}>\r\n\r\n"
            f"HTTP/1.1 {status} OK\r\n"
            f"Content-Type: application/json\r\n\r\n"
            f"{body}\r\n"
        )
    return "".join(parts) + "--batch_abc123--\r\n"


# --------------------------------------------------------------------------- #
#  Event body                                                                  #
# --------------------------------------------------------------------------- #

def test_event_body_sends_wall_clock_plus_timezone_not_utc():
    b = event_body(event_id="abc", title="Skincare", start_local="2026-03-03T07:30:00",
                   end_local="2026-03-03T07:45:00", tz_name="America/New_York",
                   event_key="abc")
    assert b["start"] == {"dateTime": "2026-03-03T07:30:00", "timeZone": "America/New_York"}
    assert "Z" not in b["start"]["dateTime"], "must not be a UTC instant"


def test_event_body_disables_google_reminders():
    """The app already pushes for every task; Google defaults would double-notify."""
    b = event_body(event_id="a", title="t", start_local="x", end_local="y",
                   tz_name="UTC", event_key="a")
    assert b["reminders"] == {"useDefault": False, "overrides": []}


def test_event_body_tags_events_as_ours():
    b = event_body(event_id="a", title="t", start_local="x", end_local="y",
                   tz_name="UTC", event_key="k")
    assert b["extendedProperties"]["private"]["maxapp"] == "1"
    assert b["extendedProperties"]["private"]["event_key"] == "k"


def test_patch_bodies_omit_the_id():
    b = event_body(event_id="", title="t", start_local="x", end_local="y",
                   tz_name="UTC", event_key="k")
    assert "id" not in b


# --------------------------------------------------------------------------- #
#  Batch encoding / parsing                                                    #
# --------------------------------------------------------------------------- #

def test_encode_includes_content_id_per_op():
    body = _encode_batch([
        BatchOp("POST", "/calendar/v3/calendars/c/events", {"summary": "x"}, "ref1"),
        BatchOp("DELETE", "/calendar/v3/calendars/c/events/ref2", None, "ref2"),
    ])
    assert "Content-ID: <ref1>" in body and "Content-ID: <ref2>" in body
    assert "POST /calendar/v3/calendars/c/events" in body
    assert "DELETE /calendar/v3/calendars/c/events/ref2" in body


def test_parse_maps_responses_back_to_our_refs():
    raw = _batch_response([("k1", 200, '{"id": "k1"}'), ("k2", 409, '{"error": "dup"}')])
    out = _parse_batch(raw)
    assert out["k1"][0] == 200
    assert out["k2"][0] == 409


@pytest.mark.asyncio
async def test_ops_are_chunked_at_the_google_limit(monkeypatch):
    n = BATCH_MAX_OPS + 5
    ops = [BatchOp("POST", "/p", {"a": 1}, f"r{i}") for i in range(n)]
    client = _install(monkeypatch, FakeClient([FakeResponse(200, ""), FakeResponse(200, "")]))
    await execute_batch("token", ops)
    assert len(client.calls) == 2, "55 ops should split into two requests"


@pytest.mark.asyncio
async def test_empty_ops_makes_no_request(monkeypatch):
    client = _install(monkeypatch, FakeClient([]))
    assert await execute_batch("token", []) == {}
    assert client.calls == []


# --------------------------------------------------------------------------- #
#  Failure handling                                                            #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_401_raises_auth_expired(monkeypatch):
    _install(monkeypatch, FakeClient([FakeResponse(401, "unauthorized")]))
    with pytest.raises(GcalAuthExpired):
        await execute_batch("token", [BatchOp("POST", "/p", {}, "r")])


@pytest.mark.asyncio
async def test_rate_limit_backs_off_then_gives_up(monkeypatch):
    import services.gcal_write as gw
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr(gw.asyncio, "sleep", fake_sleep)
    _install(monkeypatch, FakeClient([FakeResponse(429, "slow down")] * 4))
    with pytest.raises(GcalRateLimited):
        await execute_batch("token", [BatchOp("POST", "/p", {}, "r")])
    assert slept == [1.0, 2.0, 4.0], "should back off three times before abandoning"


@pytest.mark.asyncio
async def test_rate_limit_that_clears_is_retried_successfully(monkeypatch):
    import services.gcal_write as gw

    async def fake_sleep(s):
        return None

    monkeypatch.setattr(gw.asyncio, "sleep", fake_sleep)
    ok = FakeResponse(200, _batch_response([("r", 200, "{}")]))
    _install(monkeypatch, FakeClient([FakeResponse(429, ""), ok]))
    out = await execute_batch("token", [BatchOp("POST", "/p", {}, "r")])
    assert out["r"][0] == 200


@pytest.mark.asyncio
async def test_delete_calendar_treats_already_gone_as_success(monkeypatch):
    from services.gcal_write import delete_calendar
    _install(monkeypatch, FakeClient([FakeResponse(404, "")]))
    assert await delete_calendar("token", "cal-id") is True


@pytest.mark.asyncio
async def test_delete_calendar_with_no_id_is_a_noop(monkeypatch):
    from services.gcal_write import delete_calendar
    client = _install(monkeypatch, FakeClient([]))
    assert await delete_calendar("token", "") is True
    assert client.calls == []


@pytest.mark.asyncio
async def test_create_calendar_returns_the_new_id(monkeypatch):
    from services.gcal_write import create_calendar
    _install(monkeypatch, FakeClient([FakeResponse(200, "", {"id": "cal-123"})]))
    assert await create_calendar("token", tz_name="UTC") == "cal-123"


@pytest.mark.asyncio
async def test_create_calendar_failure_returns_none(monkeypatch):
    from services.gcal_write import create_calendar
    _install(monkeypatch, FakeClient([FakeResponse(500, "boom")]))
    assert await create_calendar("token", tz_name="UTC") is None


# --------------------------------------------------------------------------- #
#  Echo guard — our own events must never come back as busy time               #
# --------------------------------------------------------------------------- #

def test_ingest_skips_max_authored_events():
    """If the read path ever widens beyond `primary`, our own routine must not
    be re-ingested as busy — that would make the plan collide with itself."""
    from services.calendar_busy import _is_max_authored

    assert _is_max_authored({"raw": {"max_authored": True}, "external_event_id": None})
    assert _is_max_authored({"raw": {}, "external_event_id": "max:abc"})
    assert not _is_max_authored({"raw": {}, "external_event_id": "google-evt-1"})


def test_write_scope_is_the_narrow_app_created_one():
    """We ask for write access ONLY to calendars we create, never the user's own."""
    from services.google_integration import SCOPE_CALENDAR_APP
    assert SCOPE_CALENDAR_APP.endswith("calendar.app.created")


def test_auth_url_omits_write_scope_unless_asked_and_enabled(monkeypatch):
    import services.google_integration as gi

    monkeypatch.setattr(gi.settings, "google_client_id", "cid", raising=False)
    monkeypatch.setattr(gi.settings, "google_redirect_uri", "https://x/cb", raising=False)
    monkeypatch.setattr(gi.settings, "gcal_write_enabled", True, raising=False)

    assert "calendar.app.created" not in gi.build_auth_url("s", False)
    assert "calendar.app.created" in gi.build_auth_url("s", False, True)

    monkeypatch.setattr(gi.settings, "gcal_write_enabled", False, raising=False)
    assert "calendar.app.created" not in gi.build_auth_url("s", False, True), \
        "the flag must gate the scope even when the client asks for it"
