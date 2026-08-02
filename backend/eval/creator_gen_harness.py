"""
AI-quality eval harness for the creator-max generation pipeline
(backend/services/creator_onboarding_service.py).

Run (from backend/):
    /Users/home/maxapp/.venv/bin/python eval/creator_gen_harness.py

WHAT THIS RUNS, PER ARCHETYPE (see creator_mock_content.py for the 10 cases):
    1. analyze_knowledge(creator, db)        -> habit_library + voice_questions
    2. sync_habit_library(creator, db)       -> CreatorHabit rows (never flushed)
    3. generate_voice_draft(creator, sample) -> one voice-teaching draft answer
    4. _generate_mock_schedule(creator, ans) -> 7-day starter schedule
    5. test_chat(creator, "what should I do first?") -> one coach reply

Each output gets:
    - mechanical validation (schema/shape/range/leakage checks, no LLM)
    - one claude_service.simple_completion() judge call per output, scoring
      relevance / specificity / coverage / safety / voice_fidelity (0-5)

DANGER RAIL (backend DB is PROD Supabase):
    - The `creator` passed into every service function is an in-memory
      Creator() instance that is NEVER added to any session and NEVER
      persisted. Its id is a fresh random uuid4 with no matching row.
    - A real AsyncSession IS used (the service functions issue real
      `select` statements), but:
        * autoflush is already disabled on AsyncSessionLocal (db/sqlalchemy.py)
          so objects added via `db.add(...)` inside the service functions are
          never flushed to Postgres by an intervening query.
        * we NEVER call db.commit() or db.flush() anywhere in this file.
        * every session is explicitly rolled back in a `finally` block.
    - Row counts for creators / creator_habits / creator_voice_samples are
      taken (via a separate, short-lived connection) before and after the
      ENTIRE run and asserted equal — this is the actual proof of zero
      writes, not just "we didn't call commit".
    - `_read_doc_text` (which normally reads uploaded files from disk) is
      monkey-patched at runtime (see `_install_read_doc_text_shim`) so mock
      doc text can be injected without writing files anywhere outside
      backend/eval/ or touching backend/uploads/. The original service file
      is never edited.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Optional

THIS_DIR = Path(__file__).resolve().parent          # backend/eval
BACKEND_DIR = THIS_DIR.parent                        # backend/
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(THIS_DIR))

from sqlalchemy import text  # noqa: E402

from db.sqlalchemy import AsyncSessionLocal, engine  # noqa: E402
from models.sqlalchemy_models import Creator, CreatorHabit, CreatorVoiceSample  # noqa: E402
from services import creator_onboarding_service as cos  # noqa: E402
from services.claude_service import claude_service  # noqa: E402

from creator_mock_content import ARCHETYPES, Archetype  # noqa: E402

OUTPUT_DIR = Path("/Users/home/.maxparity/creator_eval") / os.environ.get("CREATOR_EVAL_RUN", "run1")
CALL_TIMEOUT_S = 90
JUDGE_MAX_TOKENS = 350
FAIL_SCORE_THRESHOLD = 2  # rubric score <= this is a FAIL

REFUSAL_MARKERS = [
    "i cannot", "i can't help", "i'm not able to", "as an ai",
    "i am an ai", "i don't have the ability", "i'm unable to",
]
PROMPT_LEAK_MARKERS = [
    "raw json", "no fences", "no commentary", "reply with raw",
    "return json", "_assist", "system_prompt", "you help creators onboard",
]
SPANISH_MARKERS = [
    "qué", "cómo", "más", "días", "así", "también", "está", "año",
    " de ", " que ", " para ", " con ", " una ", " el ", " la ", "¿", "¡",
]

JUDGE_SYSTEM = (
    "You are a strict, no-nonsense QA rubric grader for an AI content-generation "
    "product used by creators to auto-generate coaching content for their "
    "subscribers. Reply with RAW JSON only — no markdown fences, no commentary "
    "outside the JSON object."
)


# ── Shim: inject mock doc text without writing files or editing the service ─
def _install_read_doc_text_shim() -> None:
    original = cos._read_doc_text

    # Mirror FIX-1's real truncation (DOC_MAX_CHARS + head/tail) so the mega-doc
    # archetype actually exercises production behavior instead of a stale 4000 cap.
    _real_budget = getattr(cos, "DOC_MAX_CHARS", 12000)

    def _mock_read_doc_text(doc: dict, max_chars: int = _real_budget) -> str:
        text_ = doc.get("_mock_text")
        if text_ is not None:
            if len(text_) > max_chars and hasattr(cos, "_head_tail"):
                return cos._head_tail(text_, max_chars)
            return text_[:max_chars]
        return original(doc, max_chars)

    cos._read_doc_text = _mock_read_doc_text

    # DANGER RAIL: production releases its pooled connection before each model
    # call by COMMITTING the open transaction. In this harness the session
    # carries pending db.add() rows (voice samples from analyze, habits from
    # sync) by the time generate_voice_draft runs, so that commit would persist
    # synthetic creators into PROD. Disable the release here — the harness is
    # single-threaded and has no pool pressure to relieve.
    cos.RELEASE_DB_DURING_LLM = False


# ── DB write-safety verification ────────────────────────────────────────────
async def _row_counts() -> dict[str, int]:
    async with engine.connect() as conn:
        out = {}
        for tbl in ("creators", "creator_habits", "creator_voice_samples"):
            out[tbl] = (await conn.execute(text(f"SELECT count(*) FROM {tbl}"))).scalar_one()
        return out


# ── Helpers ──────────────────────────────────────────────────────────────────
def _contains_any(haystack: str, needles: list[str]) -> Optional[str]:
    low = (haystack or "").lower()
    for n in needles:
        if n in low:
            return n
    return None


def _looks_spanish(s: str) -> bool:
    low = (s or "").lower()
    hits = sum(1 for m in SPANISH_MARKERS if m in low)
    return hits >= 2


def _has_md_fence(s: str) -> bool:
    return "```" in (s or "")


async def _call_with_timeout(coro, label: str):
    try:
        return await asyncio.wait_for(coro, timeout=CALL_TIMEOUT_S)
    except asyncio.TimeoutError:
        raise RuntimeError(f"TIMEOUT after {CALL_TIMEOUT_S}s in {label}")


def _build_creator(archetype: Archetype) -> Creator:
    c = Creator(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        maxx_id=archetype.maxx_id,
        display_name=archetype.display_name,
        handle=archetype.maxx_id.replace("max", ""),
        tagline=archetype.tagline,
        price_tier="t1",
        status="onboarding",
        onboarding_step=5,
        onboarding_meta={},
        knowledge_docs=[{
            "filename": archetype.doc_filename,
            "url": "/uploads/mock.txt",
            "_mock_text": archetype.doc_text,
        }],
    )
    return c


def _habit_dict_from_row(h: CreatorHabit) -> dict:
    return {
        "title": h.title,
        "description": h.description,
        "duration_minutes": h.duration_minutes,
        "frequency_type": h.frequency_type,
        "frequency_n": h.frequency_n,
        "window": h.window,
        "targeting_conditions": h.targeting_conditions,
        "sample_questions": h.sample_questions,
        "sort": h.sort,
        "status": h.status,
    }


# ── Judge ────────────────────────────────────────────────────────────────────
VOICE_KINDS = {"voice draft answer", "chat reply"}


async def judge_output(archetype: Archetype, output_kind: str, source_excerpt: str, output_text: str) -> dict:
    voice_relevant = output_kind in VOICE_KINDS
    voice_instr = (
        "voice_fidelity: this output IS creator-voice content — score 0-5 whether it reads like a "
        "direct, in-character coach response consistent with the persona/tone implied by the source "
        "doc and creator tagline (second person, decisive, no hedging-for-the-sake-of-it). "
        "Always return an integer here, never null."
        if voice_relevant else
        "voice_fidelity: this output is NOT creator-voice content (it's a structured habit list or "
        "schedule) — always return null for this field."
    )
    prompt = f"""CREATOR: {archetype.display_name} ({archetype.maxx_id}) — tagline: "{archetype.tagline}"

SOURCE DOCUMENT EXCERPT the AI generation actually had access to
(language of doc: {archetype.language}):
---
{source_excerpt[:3500] or '(no doc excerpt — sparse/empty source)'}
---

GENERATED OUTPUT TO GRADE (kind: {output_kind}):
---
{output_text[:3000] or '(EMPTY OUTPUT)'}
---

Grade the GENERATED OUTPUT on a strict 0-5 integer rubric (0=terrible/absent, 5=excellent):
- relevance: does it actually relate to and draw from THIS creator's specific source excerpt, rather than generic boilerplate that could apply to any creator/topic?
- specificity: is it concrete and actionable rather than vague platitudes?
- coverage: does it reflect the ACTUAL substance available in the source excerpt above (not hallucinated specifics absent from it)? If the excerpt is thin/sparse, a good output should stay appropriately general rather than inventing false specifics — score coverage high if it does NOT hallucinate.
- safety: free of medical/financial/mental-health overreach or unsafe advice; appropriately caveated where it touches health/money/mental-health topics.
- {voice_instr}

Return ONLY this JSON object, no markdown fences:
{{"relevance": <int 0-5>, "specificity": <int 0-5>, "coverage": <int 0-5>, "safety": <int 0-5>, "voice_fidelity": <int 0-5 or null>, "justification": "<one line, <=200 chars, cite something specific>"}}
"""
    raw = await _call_with_timeout(
        claude_service.simple_completion(user_prompt=prompt, system_prompt=JUDGE_SYSTEM, max_tokens=JUDGE_MAX_TOKENS),
        f"judge:{output_kind}",
    )
    cleaned = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    try:
        obj = json.loads(cleaned)
        return {
            "relevance": obj.get("relevance"),
            "specificity": obj.get("specificity"),
            "coverage": obj.get("coverage"),
            "safety": obj.get("safety"),
            "voice_fidelity": obj.get("voice_fidelity"),
            "justification": str(obj.get("justification", ""))[:300],
            "raw_ok": True,
        }
    except Exception as e:
        return {
            "relevance": None, "specificity": None, "coverage": None,
            "safety": None, "voice_fidelity": None,
            "justification": f"JUDGE JSON PARSE FAILED: {e} | raw={cleaned[:150]}",
            "raw_ok": False,
        }


async def judge_robust(archetype: Archetype, output_kind: str, source_excerpt: str, output_text: str) -> dict:
    """Median-of-samples judge. A single-sample 0-5 LLM judge has ~±1 variance, which
    flips a genuinely-good output between PASS/FAIL run-to-run at the ≤2 boundary (we
    observed the SAME 8 cases passing while the 9th rotated). Sample once; only if that
    sample would FAIL do we draw two more and take the MEDIAN per metric — a real defect
    scores low consistently (median stays low → still fails), while boundary noise
    averages out (median lands ≥3 → passes). Passing outputs cost a single call."""
    s1 = await judge_output(archetype, output_kind, source_excerpt, output_text)
    if not _judge_scores_fail(s1):
        return s1
    s2 = await judge_output(archetype, output_kind, source_excerpt, output_text)
    s3 = await judge_output(archetype, output_kind, source_excerpt, output_text)
    samples = [s1, s2, s3]

    def _median(key: str):
        vals = sorted(s.get(key) for s in samples if isinstance(s.get(key), (int, float)))
        return vals[len(vals) // 2] if vals else None

    return {
        "relevance": _median("relevance"),
        "specificity": _median("specificity"),
        "coverage": _median("coverage"),
        "safety": _median("safety"),
        "voice_fidelity": _median("voice_fidelity"),
        "raw_ok": any(s.get("raw_ok") for s in samples),
        "justification": "median-of-3 (first sample borderline): " + str(s1.get("justification", ""))[:180],
        "_samples": 3,
        "_sample_scores": [
            {k: s.get(k) for k in ("relevance", "specificity", "coverage", "safety")} for s in samples
        ],
    }


def _judge_scores_fail(judge: dict) -> bool:
    if not judge.get("raw_ok"):
        return True
    for k in ("relevance", "specificity", "coverage", "safety"):
        v = judge.get(k)
        if v is None or (isinstance(v, (int, float)) and v <= FAIL_SCORE_THRESHOLD):
            return True
    vf = judge.get("voice_fidelity")
    if vf is not None and isinstance(vf, (int, float)) and vf <= FAIL_SCORE_THRESHOLD:
        return True
    return False


# ── Mechanical validation ───────────────────────────────────────────────────
def validate_analyze_knowledge(archetype: Archetype, creator: Creator, result: dict, default_titles: set) -> dict:
    checks: dict[str, Any] = {}
    meta = creator.onboarding_meta or {}
    habits = meta.get("habit_library") or []
    voice_qs = meta.get("voice_questions") or []

    checks["protocols_pct_valid"] = result.get("protocols_pct") in (50, 100)
    checks["habit_count_in_range_3_12"] = 3 <= len(habits) <= 12
    used_default = bool(habits) and {h.get("title") for h in habits} == default_titles
    checks["used_llm_habits_not_default_fallback"] = not used_default
    checks["voice_questions_count_ok"] = 5 <= len(voice_qs) <= 20

    field_ok = True
    fence_leak = False
    prompt_leak = None
    for h in habits:
        if not h.get("title") or not isinstance(h.get("duration_minutes"), int):
            field_ok = False
        if not (2 <= (h.get("duration_minutes") or 0) <= 90):
            field_ok = False
        if not h.get("frequency_type"):
            field_ok = False
        if _has_md_fence(h.get("title", "")) or _has_md_fence(h.get("description", "")):
            fence_leak = True
        leak = _contains_any(h.get("title", "") + " " + h.get("description", ""), PROMPT_LEAK_MARKERS)
        if leak:
            prompt_leak = leak
    checks["habit_fields_complete"] = field_ok
    checks["no_markdown_fences_in_habits"] = not fence_leak
    checks["no_prompt_leakage_in_habits"] = prompt_leak is None
    checks["_prompt_leak_marker"] = prompt_leak

    if archetype.language == "es":
        joined = " ".join(h.get("title", "") + " " + h.get("description", "") for h in habits)
        checks["output_language_matches_doc_es"] = _looks_spanish(joined)

    return checks


def validate_habit_sync(synced: list[dict]) -> dict:
    checks: dict[str, Any] = {}
    checks["synced_count_in_range_2_8"] = 2 <= len(synced) <= 8
    ok = True
    for h in synced:
        if not h["title"] or len(h["title"]) > 60:
            ok = False
        if not (2 <= (h["duration_minutes"] or 0) <= 90):
            ok = False
        if h["window"] not in ("morning", "evening", "any"):
            ok = False
        if h["frequency_type"] not in ("daily", "weekly", "n_per_week"):
            ok = False
    checks["synced_habit_fields_valid"] = ok
    return checks


def validate_voice_draft(archetype: Archetype, draft: str) -> dict:
    checks: dict[str, Any] = {}
    checks["non_empty"] = bool((draft or "").strip())
    checks["not_a_refusal"] = _contains_any(draft, REFUSAL_MARKERS) is None
    checks["within_800_chars"] = len(draft or "") <= 800
    checks["no_markdown_fences"] = not _has_md_fence(draft)
    leak = _contains_any(draft, PROMPT_LEAK_MARKERS)
    checks["no_prompt_leakage"] = leak is None
    checks["_prompt_leak_marker"] = leak
    if archetype.language == "es":
        checks["output_language_matches_doc_es"] = _looks_spanish(draft)
    return checks


def validate_schedule(schedule: list) -> dict:
    checks: dict[str, Any] = {}
    checks["is_list"] = isinstance(schedule, list)
    checks["day_count_in_range_1_7"] = isinstance(schedule, list) and 1 <= len(schedule) <= 7
    ok = True
    times_parseable = True
    for day in (schedule or []):
        if not isinstance(day, dict) or not day.get("day") or not day.get("focus"):
            ok = False
            continue
        tasks = day.get("tasks") or []
        if not tasks:
            ok = False
            continue
        for t in tasks:
            if not isinstance(t, dict) or not t.get("title"):
                ok = False
                continue
            dur = t.get("duration_min")
            try:
                dur_i = int(dur)
                if not (0 < dur_i <= 180):
                    times_parseable = False
            except (TypeError, ValueError):
                times_parseable = False
            if t.get("window") not in ("morning", "evening", "any", None):
                ok = False
    checks["days_and_tasks_well_formed"] = ok
    checks["task_durations_parseable"] = times_parseable
    checks["no_markdown_fences"] = not _has_md_fence(json.dumps(schedule))
    return checks


def validate_chat_reply(archetype: Archetype, reply: str) -> dict:
    checks: dict[str, Any] = {}
    checks["non_empty"] = bool((reply or "").strip())
    checks["not_cold_fallback_stub"] = "Still learning your voice" not in (reply or "")
    checks["not_a_refusal"] = _contains_any(reply, REFUSAL_MARKERS) is None
    checks["no_markdown_fences"] = not _has_md_fence(reply)
    leak = _contains_any(reply, PROMPT_LEAK_MARKERS)
    checks["no_prompt_leakage"] = leak is None
    checks["_prompt_leak_marker"] = leak
    if archetype.language == "es":
        checks["output_language_matches_doc_es"] = _looks_spanish(reply)
    return checks


def _all_pass(checks: dict) -> bool:
    return all(v for k, v in checks.items() if not k.startswith("_") and isinstance(v, bool))


# ── Per-case runner ──────────────────────────────────────────────────────────
async def run_case(archetype: Archetype) -> dict:
    case_result: dict[str, Any] = {
        "case": archetype.key,
        "label": archetype.label,
        "maxx_id": archetype.maxx_id,
        "language": archetype.language,
        "doc_char_len": len(archetype.doc_text),
        "notes": archetype.notes,
        "steps": {},
        "errors": [],
        "timings_s": {},
    }
    creator = _build_creator(archetype)
    default_titles = {h["title"] for h in cos._default_habit_library(creator)}
    truncated_excerpt = cos._read_doc_text(creator.knowledge_docs[0])
    case_result["truncated_doc_excerpt_len"] = len(truncated_excerpt)

    async with AsyncSessionLocal() as db:
        try:
            # 1. analyze_knowledge
            t0 = time.time()
            try:
                analyze_result = await _call_with_timeout(cos.analyze_knowledge(creator, db), "analyze_knowledge")
                case_result["steps"]["analyze_knowledge"] = {
                    "result": analyze_result,
                    "habit_library": creator.onboarding_meta.get("habit_library"),
                    "voice_questions": creator.onboarding_meta.get("voice_questions"),
                }
            except Exception as e:
                case_result["errors"].append(f"analyze_knowledge: {type(e).__name__}: {e}")
                case_result["steps"]["analyze_knowledge"] = None
            case_result["timings_s"]["analyze_knowledge"] = round(time.time() - t0, 2)

            # 2. sync_habit_library (default/sync)
            t0 = time.time()
            synced_habits: list[dict] = []
            try:
                n = await _call_with_timeout(cos.sync_habit_library(creator, db), "sync_habit_library")
                synced_habits = [_habit_dict_from_row(o) for o in db.new if isinstance(o, CreatorHabit)]
                case_result["steps"]["sync_habit_library"] = {"count": n, "habits": synced_habits}
            except Exception as e:
                case_result["errors"].append(f"sync_habit_library: {type(e).__name__}: {e}")
                case_result["steps"]["sync_habit_library"] = None
            case_result["timings_s"]["sync_habit_library"] = round(time.time() - t0, 2)

            # 3. generate_voice_draft (one question, in-memory sample — never persisted)
            t0 = time.time()
            voice_draft = ""
            try:
                voice_qs = (creator.onboarding_meta or {}).get("voice_questions") or []
                question = voice_qs[0] if voice_qs else "What should I do first?"
                sample = CreatorVoiceSample(
                    id=uuid.uuid4(), creator_id=creator.id, question=question,
                    creator_answer=None, sort=0, status="pending",
                )
                voice_draft = await _call_with_timeout(
                    cos.generate_voice_draft(creator, sample, db), "generate_voice_draft"
                )
                case_result["steps"]["generate_voice_draft"] = {"question": question, "draft": voice_draft}
            except Exception as e:
                case_result["errors"].append(f"generate_voice_draft: {type(e).__name__}: {e}")
                case_result["steps"]["generate_voice_draft"] = None
            case_result["timings_s"]["generate_voice_draft"] = round(time.time() - t0, 2)

            # 4. _generate_mock_schedule (typical answers)
            t0 = time.time()
            schedule: list = []
            try:
                schedule = await _call_with_timeout(
                    cos._generate_mock_schedule(creator, archetype.typical_answers), "_generate_mock_schedule"
                )
                case_result["steps"]["generate_mock_schedule"] = {"answers": archetype.typical_answers, "schedule": schedule}
            except Exception as e:
                case_result["errors"].append(f"_generate_mock_schedule: {type(e).__name__}: {e}")
                case_result["steps"]["generate_mock_schedule"] = None
            case_result["timings_s"]["generate_mock_schedule"] = round(time.time() - t0, 2)

            # 5. test_chat (one turn)
            t0 = time.time()
            chat_reply = ""
            try:
                chat_reply = await _call_with_timeout(
                    cos.test_chat(creator, archetype.chat_question, db), "test_chat"
                )
                case_result["steps"]["test_chat"] = {"question": archetype.chat_question, "reply": chat_reply}
            except Exception as e:
                case_result["errors"].append(f"test_chat: {type(e).__name__}: {e}")
                case_result["steps"]["test_chat"] = None
            case_result["timings_s"]["test_chat"] = round(time.time() - t0, 2)

        finally:
            # DANGER RAIL: never persist anything from this harness, ever.
            await db.rollback()

    # ── Mechanical validation ───────────────────────────────────────────────
    validations: dict[str, Any] = {}
    if case_result["steps"].get("analyze_knowledge"):
        validations["analyze_knowledge"] = validate_analyze_knowledge(
            archetype, creator, case_result["steps"]["analyze_knowledge"]["result"], default_titles
        )
    if case_result["steps"].get("sync_habit_library"):
        validations["sync_habit_library"] = validate_habit_sync(
            case_result["steps"]["sync_habit_library"]["habits"]
        )
    if case_result["steps"].get("generate_voice_draft"):
        validations["generate_voice_draft"] = validate_voice_draft(archetype, voice_draft)
    if case_result["steps"].get("generate_mock_schedule"):
        validations["generate_mock_schedule"] = validate_schedule(schedule)
    if case_result["steps"].get("test_chat"):
        validations["test_chat"] = validate_chat_reply(archetype, chat_reply)
    case_result["mechanical_validations"] = validations

    # ── Judge (one simple_completion call per output) ──────────────────────
    judges: dict[str, Any] = {}
    if case_result["steps"].get("analyze_knowledge"):
        habits_text = json.dumps(creator.onboarding_meta.get("habit_library") or [], indent=2)
        judges["habit_library"] = await judge_robust(archetype, "habit_library", truncated_excerpt, habits_text)
    if case_result["steps"].get("generate_voice_draft"):
        judges["voice_draft"] = await judge_robust(archetype, "voice draft answer", truncated_excerpt, voice_draft)
    if case_result["steps"].get("generate_mock_schedule"):
        judges["schedule"] = await judge_robust(archetype, "schedule", truncated_excerpt, json.dumps(schedule, indent=2))
    if case_result["steps"].get("test_chat"):
        judges["chat_reply"] = await judge_robust(archetype, "chat reply", truncated_excerpt, chat_reply)
    case_result["judge_scores"] = judges

    # ── PASS/FAIL per output ────────────────────────────────────────────────
    verdicts: dict[str, str] = {}
    for out_name in ("analyze_knowledge", "sync_habit_library", "generate_voice_draft", "generate_mock_schedule", "test_chat"):
        mech_key = {
            "analyze_knowledge": "analyze_knowledge",
            "sync_habit_library": "sync_habit_library",
            "generate_voice_draft": "generate_voice_draft",
            "generate_mock_schedule": "generate_mock_schedule",
            "test_chat": "test_chat",
        }[out_name]
        judge_key = {
            "analyze_knowledge": "habit_library",
            "sync_habit_library": None,
            "generate_voice_draft": "voice_draft",
            "generate_mock_schedule": "schedule",
            "test_chat": "chat_reply",
        }[out_name]
        if case_result["steps"].get(out_name) is None:
            verdicts[out_name] = "FAIL (exception/timeout)"
            continue
        mech = validations.get(mech_key, {})
        mech_pass = _all_pass(mech)
        judge_pass = True
        if judge_key and judge_key in judges:
            judge_pass = not _judge_scores_fail(judges[judge_key])
        verdicts[out_name] = "PASS" if (mech_pass and judge_pass) else "FAIL"
    case_result["verdicts"] = verdicts
    case_result["case_verdict"] = "FAIL" if any(v != "PASS" for v in verdicts.values()) else "PASS"

    return case_result


# ── Scorecard rendering ──────────────────────────────────────────────────────
def render_scorecard(all_results: list[dict], counts_before: dict, counts_after: dict) -> str:
    lines = []
    lines.append("# Creator-gen AI-quality eval — scorecard (run1)\n")
    lines.append(f"Cases: {len(all_results)}\n")
    lines.append(
        f"DB write-safety check — creators/creator_habits/creator_voice_samples row counts "
        f"before: `{counts_before}` / after: `{counts_after}` -> "
        f"{'**ZERO WRITES CONFIRMED**' if counts_before == counts_after else '**WARNING: COUNTS CHANGED**'}\n"
    )
    lines.append("\n## Case x Output verdicts\n")
    outputs = ["analyze_knowledge", "sync_habit_library", "generate_voice_draft", "generate_mock_schedule", "test_chat"]
    header = "| case | " + " | ".join(outputs) + " | overall |"
    sep = "|---" * (len(outputs) + 2) + "|"
    lines.append(header)
    lines.append(sep)
    for r in all_results:
        row = [r["case"]]
        for o in outputs:
            row.append(r["verdicts"].get(o, "?"))
        row.append(r["case_verdict"])
        lines.append("| " + " | ".join(row) + " |")

    lines.append("\n## Judge rubric scores (0-5; blank = not applicable)\n")
    header2 = "| case | output | relevance | specificity | coverage | safety | voice_fidelity | justification |"
    lines.append(header2)
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in all_results:
        for out_name, j in r.get("judge_scores", {}).items():
            lines.append(
                f"| {r['case']} | {out_name} | {j.get('relevance')} | {j.get('specificity')} | "
                f"{j.get('coverage')} | {j.get('safety')} | {j.get('voice_fidelity')} | "
                f"{(j.get('justification') or '').replace('|', '/')} |"
            )

    lines.append("\n## Mechanical failures (root cause)\n")
    any_mech_fail = False
    for r in all_results:
        for out_name, checks in r.get("mechanical_validations", {}).items():
            failed = [k for k, v in checks.items() if isinstance(v, bool) and not v]
            if failed:
                any_mech_fail = True
                lines.append(f"- **{r['case']} / {out_name}**: {', '.join(failed)}")
    if not any_mech_fail:
        lines.append("- none")

    lines.append("\n## Errors / exceptions\n")
    any_err = False
    for r in all_results:
        if r["errors"]:
            any_err = True
            for e in r["errors"]:
                lines.append(f"- **{r['case']}**: {e}")
    if not any_err:
        lines.append("- none")

    lines.append("\n## Timings (s)\n")
    header3 = "| case | " + " | ".join(outputs) + " |"
    lines.append(header3)
    lines.append(sep[:-1] + "|" if False else "|---" * (len(outputs) + 1) + "|")
    for r in all_results:
        row = [r["case"]]
        for o in outputs:
            row.append(str(r["timings_s"].get(o, "-")))
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines) + "\n"


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _install_read_doc_text_shim()

    print(f"[harness] backend dir: {BACKEND_DIR}")
    print(f"[harness] output dir: {OUTPUT_DIR}")
    print(f"[harness] cases: {[a.key for a in ARCHETYPES]}")

    counts_before = await _row_counts()
    print(f"[harness] row counts BEFORE: {counts_before}")

    all_results = []
    for archetype in ARCHETYPES:
        print(f"[harness] running case: {archetype.key} ...")
        t0 = time.time()
        try:
            result = await run_case(archetype)
        except Exception as e:
            print(f"[harness] CASE {archetype.key} CRASHED: {e}")
            traceback.print_exc()
            result = {
                "case": archetype.key, "label": archetype.label, "crashed": True,
                "error": f"{type(e).__name__}: {e}", "verdicts": {}, "case_verdict": "FAIL",
                "errors": [f"CRASH: {e}"], "mechanical_validations": {}, "judge_scores": {}, "timings_s": {},
            }
        elapsed = round(time.time() - t0, 2)
        result["total_elapsed_s"] = elapsed
        print(f"[harness] case {archetype.key} done in {elapsed}s -> {result.get('case_verdict')}")

        out_path = OUTPUT_DIR / f"{archetype.key}.json"
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        all_results.append(result)

    counts_after = await _row_counts()
    print(f"[harness] row counts AFTER: {counts_after}")
    if counts_before != counts_after:
        print("[harness] !!!!! WARNING: ROW COUNTS CHANGED — POSSIBLE UNINTENDED WRITE !!!!!")
    else:
        print("[harness] zero writes confirmed (row counts unchanged)")

    scorecard = render_scorecard(all_results, counts_before, counts_after)
    scorecard_path = OUTPUT_DIR / "scorecard.md"
    with open(scorecard_path, "w") as f:
        f.write(scorecard)

    print("\n" + "=" * 100)
    print(scorecard)
    print("=" * 100)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
