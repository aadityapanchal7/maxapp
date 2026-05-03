"""Smoke tests for the new max-doc → schedule pipeline.

These tests do NOT touch the database or call any LLM. They cover:
  - Doc parsing (front-matter + chunks + task_catalog)
  - DSL expression evaluation
  - Window resolution
  - Validator round-trip
  - Catalog filter (eligible_tasks)

Run with `pytest backend/tests/test_max_doc_pipeline.py -q`.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from datetime import time as dtime

# Allow `python backend/tests/...` style runs.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


# --------------------------------------------------------------------------- #
#  Doc loader                                                                 #
# --------------------------------------------------------------------------- #

def test_parse_skinmax_doc():
    from services.max_doc_loader import parse_max_doc, DEFAULT_MAX_DOC_DIR
    doc = parse_max_doc(DEFAULT_MAX_DOC_DIR / "skinmax.md")
    assert doc.maxx_id == "skinmax"
    assert doc.display_name
    assert doc.schedule_design.get("cadence_days") == 14
    assert any(f["id"] == "skin_concern" for f in doc.required_fields)
    assert len(doc.chunks) >= 10, f"expected 10+ chunks, got {len(doc.chunks)}"
    assert any(t.id == "skin.cleanse_am" for t in doc.tasks)
    assert any(t.id == "skin.spf" for t in doc.tasks)
    # Required-field metadata round-trip.
    sc = next(f for f in doc.required_fields if f["id"] == "skin_concern")
    assert "options" in sc and "rosacea" in sc["options"]


def test_parse_all_three_docs():
    from services.max_doc_loader import parse_all_max_docs
    docs = parse_all_max_docs()
    ids = {d.maxx_id for d in docs}
    assert {"skinmax", "hairmax", "heightmax"}.issubset(ids), ids
    for doc in docs:
        assert doc.tasks, f"{doc.maxx_id} has empty task_catalog"
        # No two tasks share the same ID
        ids_in_doc = [t.id for t in doc.tasks]
        assert len(ids_in_doc) == len(set(ids_in_doc)), f"duplicate IDs in {doc.maxx_id}"


# --------------------------------------------------------------------------- #
#  DSL                                                                        #
# --------------------------------------------------------------------------- #

def test_dsl_basic():
    from services.schedule_dsl import evaluate, evaluate_all
    ctx = {"skin_concern": "rosacea", "barrier_state": "damaged", "age": 16, "outdoor": True}
    assert evaluate("always", ctx) is True
    assert evaluate("skin_concern == rosacea", ctx) is True
    assert evaluate("skin_concern == acne", ctx) is False
    assert evaluate("barrier_state in [damaged, sensitive]", ctx) is True
    assert evaluate("age < 18", ctx) is True
    assert evaluate("age >= 22", ctx) is False
    assert evaluate("outdoor", ctx) is True
    assert evaluate("!outdoor", ctx) is False
    assert evaluate_all(["age < 18", "outdoor"], ctx) is True
    assert evaluate_all(["age < 18", "skin_concern == acne"], ctx) is False
    # AND chain
    assert evaluate("age < 18 and outdoor", ctx) is True


def test_dsl_unknown_field_is_falsy():
    from services.schedule_dsl import evaluate
    ctx = {"a": 1}
    assert evaluate("missing == 5", {}) is False
    assert evaluate("missing in [a, b]", {}) is False
    assert evaluate("missing", ctx) is False


# --------------------------------------------------------------------------- #
#  Window resolver                                                            #
# --------------------------------------------------------------------------- #

def test_window_resolver():
    from services.schedule_dsl import resolve_window, parse_clock
    wake = parse_clock("06:30")
    sleep = parse_clock("23:00")
    am_o = resolve_window("am_open", wake=wake, sleep=sleep)
    assert am_o == (6 * 60 + 40, 6 * 60 + 60)  # wake+10 .. wake+30
    pm_c = resolve_window("pm_close", wake=wake, sleep=sleep)
    # sleep_min = 23*60; pm_close = sleep-1:00 .. sleep-0:15 = 22:00 .. 22:45
    assert pm_c == (22 * 60, 22 * 60 + 45)


# --------------------------------------------------------------------------- #
#  Catalog filter                                                             #
# --------------------------------------------------------------------------- #

def test_catalog_eligible_filters_by_state():
    from services.task_catalog_service import warm_catalog, eligible_tasks, missing_required, applicable_modifiers
    asyncio.run(warm_catalog())

    # Damaged barrier user — retinoid + dermastamp must be excluded.
    state = {"skin_concern": "pigmentation", "barrier_state": "damaged", "skin_type": "combo"}
    elig = eligible_tasks("skinmax", state)
    ids = {t.id for t in elig}
    assert "skin.cleanse_am" in ids
    assert "skin.retinoid_pm" not in ids, "retinoid must be excluded for damaged barrier"
    assert "skin.dermastamp_pm" not in ids
    assert "skin.barrier_pause" in ids

    # Stable barrier + pigmentation — retinoid in
    state2 = {"skin_concern": "pigmentation", "barrier_state": "stable", "skin_type": "combo",
              "dermastamp_owned": True}
    elig2 = eligible_tasks("skinmax", state2)
    ids2 = {t.id for t in elig2}
    assert "skin.retinoid_pm" in ids2
    assert "skin.dermastamp_pm" in ids2

    # Missing required: nothing → all required fields surface.
    missing = missing_required("skinmax", {})
    miss_ids = {f["id"] for f in missing}
    assert {"skin_concern", "barrier_state", "skin_type"}.issubset(miss_ids)

    # Modifiers fire correctly
    mods = applicable_modifiers("skinmax", state)  # damaged barrier
    assert any("REPAIR" in m for m in mods)


def test_catalog_filter_for_hair_curly_loss():
    from services.task_catalog_service import eligible_tasks
    state = {
        "hair_type": "curly", "scalp_state": "normal",
        "hair_loss_signs": "yes_active", "daily_styling": True,
        "dermaroller_owned": True,
    }
    ids = {t.id for t in eligible_tasks("hairmax", state)}
    assert "hair.cowash_curly" in ids
    assert "hair.minoxidil_am" in ids
    assert "hair.minoxidil_pm" in ids
    assert "hair.microneedle_pm" in ids


# --------------------------------------------------------------------------- #
#  Validator                                                                  #
# --------------------------------------------------------------------------- #

def test_validator_fixes_collisions_and_titles():
    from services.task_catalog_service import warm_catalog
    from services.schedule_validator import validate_and_fix
    asyncio.run(warm_catalog())

    days = [{
        "tasks": [
            {"catalog_id": "skin.cleanse_am", "time": "06:45",
             "title": "this title is way too long for the calendar grid",
             "description": "ok"},
            {"catalog_id": "skin.spf", "time": "06:45", "title": "spf"},  # collision
            {"catalog_id": "skin.moisturize_am", "time": "06:46", "title": "moist"},  # collision
        ]
    }]
    clean, errs, fixed = validate_and_fix(
        maxx_id="skinmax", days=days, wake_time="06:30", sleep_time="23:00",
        user_ctx={"skin_concern": "acne", "barrier_state": "stable", "skin_type": "oily"},
        expected_day_count=1, daily_task_budget=(2, 6),
    )
    assert clean, [e.message for e in errs if e.severity == "hard"]
    times = [t["time"] for t in fixed[0]["tasks"]]
    assert len(set(times)) == 3, f"collisions not separated: {times}"
    titles = [t["title"] for t in fixed[0]["tasks"]]
    assert all(len(t) <= 28 for t in titles), titles


def test_validator_rejects_unknown_catalog_id():
    from services.task_catalog_service import warm_catalog
    from services.schedule_validator import validate_and_fix
    asyncio.run(warm_catalog())

    days = [{"tasks": [{"catalog_id": "skin.bogus_thing", "time": "07:00", "title": "x"}]}]
    clean, errs, _ = validate_and_fix(
        maxx_id="skinmax", days=days, wake_time="07:00", sleep_time="23:00",
        user_ctx={}, expected_day_count=1,
    )
    assert not clean
    assert any(e.code == "unknown_catalog_id" for e in errs)


def test_validator_blocks_antagonistic_pair():
    from services.task_catalog_service import warm_catalog
    from services.schedule_validator import validate_and_fix
    asyncio.run(warm_catalog())

    days = [{"tasks": [
        {"catalog_id": "skin.retinoid_pm", "time": "21:30", "title": "tret"},
        {"catalog_id": "skin.dermastamp_pm", "time": "21:45", "title": "stamp"},
    ]}]
    clean, errs, _ = validate_and_fix(
        maxx_id="skinmax", days=days, wake_time="07:00", sleep_time="23:00",
        user_ctx={"skin_concern": "pigmentation", "barrier_state": "stable",
                  "skin_type": "combo", "dermastamp_owned": True},
        expected_day_count=1,
    )
    assert not clean
    assert any(e.code == "antagonistic_pair" for e in errs)


# --------------------------------------------------------------------------- #
#  Multi-module collision                                                     #
# --------------------------------------------------------------------------- #

def test_multi_module_collision_separates_times():
    from services.multi_module_collision import reconcile_schedules
    bundle = {
        "skinmax": [{"tasks": [
            {"catalog_id": "skin.cleanse_am", "time": "06:45", "duration_min": 3, "intensity": 0.1},
        ]}],
        "hairmax": [{"tasks": [
            {"catalog_id": "hair.minoxidil_am", "time": "06:45", "duration_min": 3, "intensity": 0.6},
        ]}],
    }
    out = reconcile_schedules(bundle)
    times = sorted([
        out["skinmax"][0]["tasks"][0]["time"],
        out["hairmax"][0]["tasks"][0]["time"],
    ])
    assert times[0] != times[1], "tasks at same time should be separated"


if __name__ == "__main__":
    # Allow direct execution without pytest.
    import inspect
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            print(f"running {name}...", end=" ")
            try:
                fn()
                print("OK")
            except Exception as e:
                print(f"FAIL: {e}")
                raise
    print("all tests passed")
