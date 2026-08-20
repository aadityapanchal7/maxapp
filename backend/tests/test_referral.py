"""Referral / promo code system (RALPH_REFERRAL Phase 7).

Covers: validate (happy/expired/max/per-user/self-referral), redeem atomicity
(the conditional count-guard + one-per-user), free-comp entitlement + idempotency,
discount path inert when ids/flag unset, platform split, and production-gating
(feature flag OFF). Pure-logic + monkeypatched-DB style (no live DB), matching
tests/test_personalization.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

import services.referral_service as R
from models.sqlalchemy_models import ReferralCode, ReferralRedemption, User


def _code(**kw) -> ReferralCode:
    base = dict(
        id=uuid4(), code="ANISH20", kind="free_comp", granted_tier="premium",
        is_active=True, redemption_count=0, per_user_limit=1, max_redemptions=None,
        starts_at=None, expires_at=None, owner_user_id=None,
        discount_kind=None, discount_value=None,
        stripe_promotion_code=None, stripe_coupon_id=None, stripe_price_id=None,
        apple_offer_code=None, apple_offer_id=None, campaign=None,
    )
    base.update(kw)
    return ReferralCode(**base)


def _user(**kw) -> User:
    base = dict(id=uuid4(), email="u@x.com", password_hash="x", is_paid=False)
    base.update(kw)
    return User(**base)


# --------------------------------------------------------------------------- #
#  Pure logic                                                                  #
# --------------------------------------------------------------------------- #

def test_normalize_code_is_case_insensitive_and_strips_noise():
    assert R.normalize_code(" anish-20! ") == "ANISH20"
    assert R.normalize_code("VIP_2024") == "VIP2024"
    assert R.normalize_code(None) == ""


def test_window_state_covers_lifecycle():
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert R.window_state(_code(), now) is None
    assert R.window_state(_code(is_active=False), now) == "inactive"
    assert R.window_state(_code(starts_at=now + timedelta(days=1)), now) == "not_started"
    assert R.window_state(_code(expires_at=now - timedelta(days=1)), now) == "expired"
    assert R.window_state(_code(max_redemptions=2, redemption_count=2), now) == "max_reached"
    assert R.window_state(_code(max_redemptions=2, redemption_count=1), now) is None


def test_is_full_comp_detects_comp_and_100_percent_discount():
    assert R._is_full_comp(_code(kind="free_comp"))
    assert R._is_full_comp(_code(kind="discount", discount_kind="percent", discount_value=100))
    assert not R._is_full_comp(_code(kind="discount", discount_kind="percent", discount_value=20))
    assert not R._is_full_comp(_code(kind="referral", granted_tier=None))


def test_discount_payload_labels():
    p = R._discount_payload(_code(kind="discount", discount_kind="percent", discount_value=20))
    assert p == {"kind": "percent", "value": 20.0, "label": "20% off"}
    f = R._discount_payload(_code(kind="discount", discount_kind="fixed", discount_value=5))
    assert f["label"] == "$5 off"


# --------------------------------------------------------------------------- #
#  Discount seam — platform split, inert + safe when flag/ids unset (RC5)       #
# --------------------------------------------------------------------------- #

def test_discount_inert_when_flag_off(monkeypatch):
    monkeypatch.setattr(R.settings, "referral_discounts_enabled", False, raising=False)
    code = _code(kind="discount", discount_kind="percent", discount_value=20,
                 apple_offer_code="OFFER1", stripe_promotion_code="promo_1")
    for plat in ("ios", "web", None):
        t = R._discount_redemption_targets(code, plat)
        assert t["discount_status"] == "coming_soon"
        # NEVER surfaces a price/offer to charge when the seam is off
        assert "apple_offer_code" not in t and "stripe_promotion_code" not in t


def test_discount_ios_uses_apple_offer_only(monkeypatch):
    monkeypatch.setattr(R.settings, "referral_discounts_enabled", True, raising=False)
    code = _code(kind="discount", discount_kind="percent", discount_value=20,
                 apple_offer_code="OFFER1", stripe_promotion_code="promo_1")
    t = R._discount_redemption_targets(code, "ios")
    assert t["discount_status"] == "apple_offer"
    assert t["apple_offer_code"] == "OFFER1"
    # iOS must NOT leak the Stripe price (Apple compliance)
    assert "stripe_promotion_code" not in t


def test_discount_web_uses_stripe(monkeypatch):
    monkeypatch.setattr(R.settings, "referral_discounts_enabled", True, raising=False)
    code = _code(kind="discount", discount_kind="percent", discount_value=20,
                 stripe_promotion_code="promo_1")
    t = R._discount_redemption_targets(code, "web")
    assert t["discount_status"] == "stripe"
    assert t["stripe_promotion_code"] == "promo_1"


def test_discount_enabled_but_ids_unset_is_inert(monkeypatch):
    monkeypatch.setattr(R.settings, "referral_discounts_enabled", True, raising=False)
    code = _code(kind="discount", discount_kind="percent", discount_value=20)  # no ids
    assert R._discount_redemption_targets(code, "ios")["discount_status"] == "coming_soon"
    assert R._discount_redemption_targets(code, "web")["discount_status"] == "coming_soon"


# --------------------------------------------------------------------------- #
#  Fake DB for redeem/validate                                                 #
# --------------------------------------------------------------------------- #

class _IncrResult:
    def __init__(self, ok): self._ok = ok
    def fetchone(self): return (1,) if self._ok else None


class _FakeDB:
    """Emulates exactly the ops redeem_code performs. `_load_code` /
    `_existing_redemption` are monkeypatched separately; this handles the atomic
    UPDATE, add/flush/commit/get."""
    def __init__(self, user, *, increment_ok=True, dup_on_flush=False):
        self.user = user
        self.increment_ok = increment_ok
        self.dup_on_flush = dup_on_flush
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, stmt, params=None):
        # Only the atomic count UPDATE reaches here (selects are patched out).
        return _IncrResult(self.increment_ok)

    def add(self, obj): self.added.append(obj)

    async def flush(self):
        if self.dup_on_flush:
            raise IntegrityError("dup", {}, Exception("unique"))

    async def get(self, model, pk): return self.user

    async def commit(self): self.committed = True

    async def rollback(self): self.rolled_back = True


@pytest.fixture(autouse=True)
def _enable_referrals(monkeypatch):
    monkeypatch.setattr(R.settings, "referrals_enabled", True, raising=False)
    monkeypatch.setattr(R.settings, "referral_rewards_enabled", False, raising=False)


def _patch_loaders(monkeypatch, code, existing=None):
    async def _load(db, c): return code
    async def _exist(db, cid, uid): return existing
    monkeypatch.setattr(R, "_load_code", _load)
    monkeypatch.setattr(R, "_existing_redemption", _exist)


def _patch_activate(monkeypatch):
    calls = {}
    async def _fake_activate(user_id, sub_id, db, **kw):
        calls.update(kw); calls["user_id"] = user_id
        db.user.is_paid = True
        db.user.subscription_tier = kw.get("subscription_tier")
        db.user.subscription_status = kw.get("subscription_status")
        db.user.billing_provider = kw.get("billing_provider")
    import api.payments as P
    monkeypatch.setattr(P, "_activate_user", _fake_activate)
    return calls


# --------------------------------------------------------------------------- #
#  redeem — free comp                                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_free_comp_grants_entitlement_and_bypasses_paywall(monkeypatch):
    user = _user()
    code = _code(kind="free_comp", granted_tier="premium")
    _patch_loaders(monkeypatch, code)
    calls = _patch_activate(monkeypatch)
    db = _FakeDB(user)
    out = await R.redeem_code(db, user, "anish20", "ios")
    assert out["result"] == "comped" and out["free"] is True
    # entitlement granted server-side via _activate_user (client never self-grants)
    assert calls["subscription_tier"] == "premium"
    assert calls["subscription_status"] == "comped"
    assert calls["billing_provider"] == "referral_comp"
    assert user.is_paid is True
    # audited + attributed + committed
    assert any(isinstance(o, ReferralRedemption) for o in db.added)
    assert user.referred_by_code_id == code.id
    assert db.committed is True


@pytest.mark.asyncio
async def test_default_comp_cash99_is_time_boxed_to_one_week(monkeypatch):
    """CASH99 (built-in launch comp) = 1 week of premium from redemption, NOT a
    lifetime grant — the entitlement must carry a subscription_end_date ~7 days
    out even though the code row itself never expires."""
    user = _user()
    code = _code(code="CASH99", kind="free_comp", granted_tier="premium",
                 campaign="launch", expires_at=None)
    _patch_loaders(monkeypatch, code)
    calls = _patch_activate(monkeypatch)
    db = _FakeDB(user)
    before = datetime.now(timezone.utc)
    out = await R.redeem_code(db, user, "CASH99", "ios")
    after = datetime.now(timezone.utc)
    assert out["result"] == "comped" and out["free"] is True
    end = calls["subscription_end_date"]
    assert end is not None, "CASH99 must be time-boxed, not lifetime"
    assert before + timedelta(days=R.DEFAULT_COMP_GRANT_DAYS) <= end <= after + timedelta(days=R.DEFAULT_COMP_GRANT_DAYS)


@pytest.mark.asyncio
async def test_bespoke_free_comp_without_expiry_stays_unlimited(monkeypatch):
    """Only the built-in DEFAULT_COMP_CODES get the 7-day box — a bespoke comp
    code with no expiry keeps its existing unlimited semantics."""
    user = _user()
    code = _code(code="VIPFOREVER", kind="free_comp", granted_tier="premium", expires_at=None)
    _patch_loaders(monkeypatch, code)
    calls = _patch_activate(monkeypatch)
    db = _FakeDB(user)
    out = await R.redeem_code(db, user, "VIPFOREVER", "ios")
    assert out["result"] == "comped"
    assert calls["subscription_end_date"] is None


@pytest.mark.asyncio
async def test_default_comp_respects_sooner_code_expiry(monkeypatch):
    """If CASH99's row somehow carries an expiry SOONER than 7 days out, the
    sooner date wins (never grant past the code's own window)."""
    user = _user()
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    code = _code(code="CASH99", kind="free_comp", granted_tier="premium", expires_at=soon)
    _patch_loaders(monkeypatch, code)
    calls = _patch_activate(monkeypatch)
    db = _FakeDB(user)
    out = await R.redeem_code(db, user, "CASH99", "ios")
    assert out["result"] == "comped"
    assert calls["subscription_end_date"] == soon


@pytest.mark.asyncio
async def test_default_comp_is_re_redeemable_with_fresh_week(monkeypatch):
    """CASH99 can be redeemed UNLIMITED times by the same user: a prior
    redemption row must not short-circuit to the cached payload, and each
    re-redemption re-grants a fresh 7-day window (reusing the audit row)."""
    user = _user(is_paid=True, billing_provider="referral_comp",
                 subscription_end_date=datetime.now(timezone.utc) - timedelta(days=1))  # expired comp
    code = _code(code="CASH99", kind="free_comp", granted_tier="premium", campaign="launch")
    prior = ReferralRedemption(id=uuid4(), code_id=code.id, user_id=user.id,
                               kind_at_redemption="free_comp", result="comped", platform="ios")
    _patch_loaders(monkeypatch, code, existing=prior)
    calls = _patch_activate(monkeypatch)
    db = _FakeDB(user)
    before = datetime.now(timezone.utc)
    out = await R.redeem_code(db, user, "CASH99", "ios")
    assert out["result"] == "comped"
    assert not out.get("idempotent"), "re-redemption must RE-GRANT, not return the cached result"
    end = calls["subscription_end_date"]
    assert end is not None and end >= before + timedelta(days=R.DEFAULT_COMP_GRANT_DAYS - 1)
    # audit row reused, never a second insert (unique constraint forbids it)
    assert not any(isinstance(o, ReferralRedemption) for o in db.added)


@pytest.mark.asyncio
async def test_default_comp_allows_expired_store_subscriber(monkeypatch):
    """A LAPSED Apple/Stripe subscriber may redeem a comp — is_paid stays True
    after expiry, and the old blanket is_paid check wrongly locked them out."""
    user = _user(is_paid=True, billing_provider="apple",
                 subscription_end_date=datetime.now(timezone.utc) - timedelta(days=3))
    code = _code(code="CASH99", kind="free_comp", granted_tier="premium")
    _patch_loaders(monkeypatch, code)
    calls = _patch_activate(monkeypatch)
    out = await R.redeem_code(_FakeDB(user), user, "CASH99", "ios")
    assert out["result"] == "comped"
    assert calls["subscription_end_date"] is not None


@pytest.mark.asyncio
async def test_comp_still_refused_for_active_store_subscriber(monkeypatch):
    """A CURRENTLY-ACTIVE store subscription must never be stomped by a comp."""
    user = _user(is_paid=True, billing_provider="apple",
                 subscription_end_date=datetime.now(timezone.utc) + timedelta(days=20))
    code = _code(code="CASH99", kind="free_comp", granted_tier="premium")
    _patch_loaders(monkeypatch, code)
    _patch_activate(monkeypatch)
    with pytest.raises(R.ReferralError) as e:
        await R.redeem_code(_FakeDB(user), user, "CASH99", "ios")
    assert e.value.reason == "already_entitled"


@pytest.mark.asyncio
async def test_bespoke_comp_keeps_one_per_user(monkeypatch):
    """Non-default comps keep the one-per-user gate: a second redeem returns
    the cached idempotent payload and never re-activates."""
    user = _user()
    code = _code(code="VIPCODE", kind="free_comp", granted_tier="premium")
    prior = ReferralRedemption(id=uuid4(), code_id=code.id, user_id=user.id,
                               kind_at_redemption="free_comp", result="comped", platform="ios")
    _patch_loaders(monkeypatch, code, existing=prior)
    calls = _patch_activate(monkeypatch)
    out = await R.redeem_code(_FakeDB(user), user, "VIPCODE", "ios")
    assert out.get("idempotent") is True
    assert "subscription_end_date" not in calls, "cached path must not re-activate"


@pytest.mark.asyncio
async def test_validate_allows_reentry_of_default_comp(monkeypatch):
    """validate() must not report already_used for CASH99 — the UI's Apply
    button has to light up on re-entry."""
    user = _user()
    code = _code(code="CASH99", kind="free_comp", granted_tier="premium")
    prior = ReferralRedemption(id=uuid4(), code_id=code.id, user_id=user.id,
                               kind_at_redemption="free_comp", result="comped", platform="ios")
    _patch_loaders(monkeypatch, code, existing=prior)
    out = await R.validate_code(_FakeDB(user), "CASH99", user_id=str(user.id))
    assert out["valid"] is True and out["free"] is True


@pytest.mark.asyncio
async def test_redeem_disabled_flag_blocks(monkeypatch):
    monkeypatch.setattr(R.settings, "referrals_enabled", False, raising=False)
    user = _user()
    with pytest.raises(R.ReferralError) as e:
        await R.redeem_code(_FakeDB(user), user, "anish20", "ios")
    assert e.value.reason == "disabled"


@pytest.mark.asyncio
async def test_redeem_self_referral_rejected(monkeypatch):
    user = _user()
    code = _code(owner_user_id=user.id)
    _patch_loaders(monkeypatch, code)
    with pytest.raises(R.ReferralError) as e:
        await R.redeem_code(_FakeDB(user), user, "anish20", "web")
    assert e.value.reason == "self_referral"


@pytest.mark.asyncio
async def test_redeem_already_entitled_rejected(monkeypatch):
    user = _user(is_paid=True)
    _patch_loaders(monkeypatch, _code(kind="free_comp"))
    with pytest.raises(R.ReferralError) as e:
        await R.redeem_code(_FakeDB(user), user, "anish20", "ios")
    assert e.value.reason == "already_entitled"


@pytest.mark.asyncio
async def test_redeem_idempotent_one_per_user(monkeypatch):
    user = _user()
    code = _code(kind="free_comp")
    existing = ReferralRedemption(id=uuid4(), code_id=code.id, user_id=user.id,
                                  kind_at_redemption="free_comp", result="comped")
    _patch_loaders(monkeypatch, code, existing=existing)
    calls = _patch_activate(monkeypatch)
    db = _FakeDB(user)
    out = await R.redeem_code(db, user, "anish20", "ios")
    assert out["idempotent"] is True and out["result"] == "comped"
    # second redemption did NOT re-grant or double-add
    assert "user_id" not in calls
    assert db.added == []


@pytest.mark.asyncio
async def test_redeem_atomic_guard_blocks_when_max_reached(monkeypatch):
    # Simulate the conditional UPDATE consuming the last slot elsewhere -> 0 rows.
    user = _user()
    _patch_loaders(monkeypatch, _code(kind="free_comp", max_redemptions=1))
    db = _FakeDB(user, increment_ok=False)
    with pytest.raises(R.ReferralError) as e:
        await R.redeem_code(db, user, "anish20", "ios")
    assert e.value.reason == "max_reached"
    assert db.rolled_back is True


@pytest.mark.asyncio
async def test_redeem_unique_race_falls_back_to_idempotent(monkeypatch):
    user = _user()
    code = _code(kind="free_comp")
    existing = ReferralRedemption(id=uuid4(), code_id=code.id, user_id=user.id,
                                  kind_at_redemption="free_comp", result="comped")
    # First existence check: None (race); flush raises unique; re-check finds it.
    seq = [None, existing]
    async def _exist(db, cid, uid): return seq.pop(0) if seq else existing
    async def _load(db, c): return code
    monkeypatch.setattr(R, "_load_code", _load)
    monkeypatch.setattr(R, "_existing_redemption", _exist)
    db = _FakeDB(user, dup_on_flush=True)
    out = await R.redeem_code(db, user, "anish20", "ios")
    assert out["idempotent"] is True and out["result"] == "comped"


@pytest.mark.asyncio
async def test_redeem_discount_inert_when_seam_off(monkeypatch):
    monkeypatch.setattr(R.settings, "referral_discounts_enabled", False, raising=False)
    user = _user()
    code = _code(kind="discount", granted_tier=None, discount_kind="percent",
                 discount_value=20, stripe_promotion_code="promo_1")
    _patch_loaders(monkeypatch, code)
    db = _FakeDB(user)
    out = await R.redeem_code(db, user, "save20", "web")
    assert out["result"] == "discount_applied"
    assert out["discount_status"] == "coming_soon"   # never charges a wrong amount
    assert user.is_paid is False                      # discount != entitlement grant
    assert db.committed is True


@pytest.mark.asyncio
async def test_validate_happy_and_failures(monkeypatch):
    code = _code(kind="free_comp")
    _patch_loaders(monkeypatch, code)
    out = await R.validate_code(_FakeDB(_user()), "anish20")
    assert out["valid"] is True and out["free"] is True

    async def _load_none(db, c): return None
    monkeypatch.setattr(R, "_load_code", _load_none)
    out = await R.validate_code(_FakeDB(_user()), "nope")
    assert out["valid"] is False and out["reason"] == "not_found"


@pytest.mark.asyncio
async def test_validate_expired(monkeypatch):
    code = _code(expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    _patch_loaders(monkeypatch, code)
    out = await R.validate_code(_FakeDB(_user()), "anish20")
    assert out["valid"] is False and out["reason"] == "expired"


# --------------------------------------------------------------------------- #
#  Endpoint gating (RC8/RC9) — feature flag OFF => 404 (byte-identical absent)  #
# --------------------------------------------------------------------------- #

def _client(monkeypatch, *, enabled: bool):
    from fastapi.testclient import TestClient
    from api.referral import router
    from fastapi import FastAPI
    from db.sqlalchemy import get_db
    from middleware.auth_middleware import get_current_user
    import api.referral as RR

    monkeypatch.setattr(RR.settings, "referrals_enabled", enabled, raising=False)
    app = FastAPI()
    app.include_router(router, prefix="/api")

    async def _fake_user(): return {"id": str(uuid4()), "is_paid": False}
    async def _fake_db(): yield _FakeDB(_user())
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


def test_endpoints_404_when_flag_off(monkeypatch):
    c = _client(monkeypatch, enabled=False)
    assert c.post("/api/referral/validate", json={"code": "X"}).status_code == 404
    assert c.post("/api/referral/redeem", json={"code": "X"}).status_code == 404


def test_validate_endpoint_works_when_enabled(monkeypatch):
    async def _val(db, code, user_id=None):
        return {"valid": True, "kind": "free_comp", "free": True, "message": "ok"}
    monkeypatch.setattr(R, "validate_code", _val)
    c = _client(monkeypatch, enabled=True)
    r = c.post("/api/referral/validate", json={"code": "ANISH20"})
    assert r.status_code == 200 and r.json()["free"] is True
