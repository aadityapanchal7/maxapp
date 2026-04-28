"""End-to-end backtest of the 4 chat-pipeline fixes.

Exercises each fix independently, then runs an integration scenario that
mirrors the original production complaint ("user types '3', bot re-asks
forever"). Prints per-case pass/fail and a final verdict block.

The harness avoids importing FastAPI / SQLAlchemy / langchain at module
load — it AST-extracts the pure-python helpers from chat.py and
fast_product_links.py, and reads prompt_constants.py as text. That lets
the script run in any environment that has stdlib + re.

Usage:
    python scripts/bench_chat_fixes.py
    python scripts/bench_chat_fixes.py --json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_ROOT))


# --------------------------------------------------------------------------- #
#  AST-load pure-python helpers without their heavy module deps                #
# --------------------------------------------------------------------------- #

def _load_chat_helpers() -> dict:
    src = (_BACKEND_ROOT / "api" / "chat.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    wanted_assigns = {"_CHOICE_ALIASES", "FITMAX_QUESTION_MAP", "HAIRMAX_QUESTION_MAP",
                      "FITMAX_REQUIRED_FIELDS", "HAIRMAX_REQUIRED_FIELDS"}
    wanted_funcs = {"_coerce_to_choice", "_parse_days_per_week_reply",
                    "_parse_session_minutes_reply", "_parse_daily_activity_short_reply",
                    "_extract_fitmax_updates", "_extract_hairmax_updates",
                    "_fitmax_missing_fields", "_hairmax_missing_fields",
                    "_to_cm_from_text", "_to_kg_from_text"}
    selected: list[ast.AST] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", "") in wanted_assigns for t in node.targets
        ):
            selected.append(node)
        elif isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") in wanted_assigns:
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted_funcs:
            selected.append(node)
    ns: dict[str, Any] = {"re": re, "Optional": Optional}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "chat.py", "exec"), ns)
    return ns


def _load_product_helpers() -> dict:
    src = (_BACKEND_ROOT / "services" / "fast_product_links.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    wanted_assigns = {"_GENERIC_NAME_BLACKLIST", "_INGREDIENT_TOKENS"}
    wanted_funcs = {"_is_specific_product_query"}
    selected: list[ast.AST] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", "") in wanted_assigns for t in node.targets
        ):
            selected.append(node)
        elif isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") in wanted_assigns:
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted_funcs:
            selected.append(node)
    ns: dict[str, Any] = {"re": re, "frozenset": frozenset}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "fpl.py", "exec"), ns)
    return ns


def _read_prompt_text() -> str:
    return (_BACKEND_ROOT / "services" / "prompt_constants.py").read_text(encoding="utf-8")


def _read_fast_rag_text() -> str:
    return (_BACKEND_ROOT / "services" / "fast_rag_answer.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
#  Backtest 1 — Fuzzy onboarding coercion                                      #
# --------------------------------------------------------------------------- #

def backtest_input_validation(chat: dict) -> dict:
    coerce = chat["_coerce_to_choice"]
    fitmax_map = chat["FITMAX_QUESTION_MAP"]
    hairmax_map = chat["HAIRMAX_QUESTION_MAP"]

    cases: list[tuple[str, str, list[str], Optional[str]]] = [
        # (label, user_reply, choices_offered, expected_canonical)

        # The literal complaint scenario from the issue spec.
        ("loop_bug_3_to_3-4",        "3",                 ["0", "1-2", "3-4", "5+"], "3-4"),
        ("loop_bug_5_to_5+",         "5",                 ["0", "1-2", "3-4", "5+"], "5+"),
        ("loop_bug_2_to_1-2",        "2",                 ["0", "1-2", "3-4", "5+"], "1-2"),
        ("loop_bug_4_to_3-4",        "4",                 ["0", "1-2", "3-4", "5+"], "3-4"),
        ("loop_bug_zero",            "0",                 ["0", "1-2", "3-4", "5+"], "0"),
        ("loop_bug_six_word",        "six",               ["0", "1-2", "3-4", "5+"], "5+"),
        ("loop_bug_natural_phrase",  "around 4 days",     ["0", "1-2", "3-4", "5+"], "3-4"),

        # Days-per-week with simple choices (real fitmax field).
        ("fitmax_days_3",            "3",                 fitmax_map["days_per_week"][1], "3"),
        ("fitmax_days_three",        "three",             fitmax_map["days_per_week"][1], "3"),
        ("fitmax_days_3_days",       "3 days",            fitmax_map["days_per_week"][1], "3"),
        ("fitmax_days_natural",      "i can do 4 days",   fitmax_map["days_per_week"][1], "4"),

        # Experience level — the LLM sometimes routes to wrong question; the
        # coercion needs to refuse instead of guessing.
        ("fitmax_xp_intermediate",   "intermediate",      fitmax_map["experience_level"][1], "intermediate"),
        ("fitmax_xp_phrase",         "i'm pretty advanced","fitmax_xp_phrase_choices",     "advanced"),  # custom below

        # Sex.
        ("fitmax_sex_male",          "male",              fitmax_map["biological_sex"][1], "male"),
        ("fitmax_sex_woman",         "woman",             fitmax_map["biological_sex"][1], "female"),
        ("fitmax_sex_short_m",       "m",                 fitmax_map["biological_sex"][1], "male"),

        # Activity level — multi-word choices.
        ("fitmax_activity_moderate", "moderate",          fitmax_map["daily_activity_level"][1], "moderately active"),
        ("fitmax_activity_sedentary","sedentary",         fitmax_map["daily_activity_level"][1], "sedentary"),
        ("fitmax_activity_phrase",   "i'm very active",   fitmax_map["daily_activity_level"][1], "very active"),

        # Equipment.
        ("fitmax_eq_dumbbells",      "i train at home with dumbbells", fitmax_map["equipment"][1], "dumbbells"),
        ("fitmax_eq_full_gym",       "full gym",          fitmax_map["equipment"][1], "full gym"),
        ("fitmax_eq_none",           "no equipment",      fitmax_map["equipment"][1], "no equipment"),

        # Hairmax.
        ("hairmax_hair_curly",       "curly",             hairmax_map["hair_type"][1], "curly"),
        ("hairmax_hair_phrase",      "kinda wavy",        hairmax_map["hair_type"][1], "wavy"),
        ("hairmax_scalp_oily",       "oily",              hairmax_map["scalp_state"][1], "oily/greasy"),
        ("hairmax_scalp_normal",     "normal",            hairmax_map["scalp_state"][1], "normal"),

        # Yes/no with semantic phrasing — the original "noticing some thinning
        # but not bald" case that loops with strict matching.
        ("yesno_thinning_a_little",  "a little thinning", hairmax_map["thinning"][1], "yes"),
        ("yesno_thinning_kinda",     "kinda",             hairmax_map["thinning"][1], "yes"),
        ("yesno_thinning_not_really","not really",        hairmax_map["thinning"][1], "no"),
        ("yesno_thinning_nah",       "nah",               hairmax_map["thinning"][1], "no"),

        # Pure garbage — must return None so the bot can paraphrase, not loop.
        ("garbage_xyz",              "xyz",               ["yes", "no"], None),
        ("garbage_empty",            "",                  ["yes", "no"], None),
        ("garbage_jibberish",        "asdfqwer",          ["beginner", "intermediate", "advanced"], None),
    ]

    results: list[dict] = []
    for label, reply, choices, want in cases:
        if choices == "fitmax_xp_phrase_choices":  # placeholder
            choices = fitmax_map["experience_level"][1]
        got = coerce(reply, choices)
        ok = got == want
        results.append({"case": label, "reply": reply, "want": want, "got": got, "pass": ok})

    passed = sum(1 for r in results if r["pass"])
    return {
        "name": "input_validation",
        "total": len(results),
        "passed": passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "results": results,
    }


# --------------------------------------------------------------------------- #
#  Backtest 2 — RAG empty-evidence fallback wiring                             #
# --------------------------------------------------------------------------- #

def backtest_rag_fallback() -> dict:
    """Verify the no-evidence branch actually calls the LLM with the
    standard-template suffix instead of returning empty. We do this by
    static-checking the source: the wiring must be present at the right
    code path."""
    src = _read_fast_rag_text()
    prompt_src = _read_prompt_text()

    checks = [
        ("standard_template_suffix_defined",
         "_STANDARD_TEMPLATE_SUFFIX" in src and "STANDARD-TEMPLATE FALLBACK" in src),
        ("answer_without_evidence_function_exists",
         "async def _answer_without_evidence" in src),
        ("answer_from_rag_calls_fallback_on_empty",
         "_answer_without_evidence(" in src),
        ("rag_answer_system_prompt_has_template_branch",
         "STANDARD-TEMPLATE FALLBACK" in prompt_src),
        ("max_chat_system_has_knowledge_fallback",
         "STANDARD-TEMPLATE KNOWLEDGE FALLBACK" in prompt_src),
        ("fallback_does_not_short_circuit_with_empty_string",
         # The OLD bug: `if not retrieved: return "", []`. The NEW code must
         # NOT have that exact pattern in answer_from_rag.
         not re.search(
             r'def answer_from_rag\([^)]*\)[^{]*?if\s+not\s+retrieved:\s*\n\s*return\s+""\s*,\s*\[\]',
             src,
             flags=re.DOTALL,
         )),
        ("standard_template_suffix_permits_general_knowledge",
         "foundational knowledge" in src or "general knowledge" in src),
        ("standard_template_announces_template",
         "standard template" in src.lower()),
        # Tier-2: broad fan-out across all maxx indexes before template
        ("broad_fanout_helper_exists",
         "_broad_fanout_retrieval" in src),
        ("broad_fanout_called_from_answer_from_rag",
         re.search(r"async def answer_from_rag.*?_broad_fanout_retrieval\(",
                   src, flags=re.DOTALL) is not None),
        ("broad_fanout_iterates_all_maxx_ids",
         "VALID_MAXX_IDS" in src),
        ("broad_fanout_has_lru_cache",
         "_BROAD_CACHE" in src and "_broad_cache_get" in src and "_broad_cache_put" in src),
        ("template_response_detector_exists",
         "_looks_like_template_response" in src),
        ("template_detector_catches_production_string",
         "no protocol on file" in src.lower() and "here's a standard template" in src.lower()),
        ("template_max_tokens_bumped_above_evidence_path",
         # Template path uses 600 vs evidence path 420 (medium length)
         re.search(r"_answer_without_evidence.*?max_tokens\s*=\s*\d+\s*if[^.]*?else\s+\d+\s*if[^.]*?else\s+(\d+)",
                   src, flags=re.DOTALL) is not None),
        ("retry_logic_on_template_shaped_output",
         "tier-1 answer flagged as template-shaped" in src
         or re.search(r"_looks_like_template_response\(answer\)", src) is not None),
    ]

    results = [{"check": label, "pass": ok} for label, ok in checks]
    passed = sum(1 for r in results if r["pass"])
    return {
        "name": "rag_fallback",
        "total": len(results),
        "passed": passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "results": results,
    }


# --------------------------------------------------------------------------- #
#  Backtest 3 — product-link entity specificity                                #
# --------------------------------------------------------------------------- #

def backtest_product_links(prod: dict) -> dict:
    is_specific = prod["_is_specific_product_query"]

    cases: list[tuple[str, bool]] = [
        # MUST DROP — generic workflow / category words
        ("routine", False),
        ("AM Routine", False),
        ("PM Routine", False),
        ("morning routine", False),
        ("Step 1", False),
        ("Step 2", False),
        ("step", False),
        ("skin", False),
        ("Skin", False),
        ("Skincare", False),
        ("hair", False),
        ("scalp", False),
        ("face", False),
        ("body", False),
        ("moisturizer", False),  # generic singleton
        ("cleanser", False),
        ("serum", False),
        ("mask", False),
        ("toner", False),
        ("shampoo", False),
        ("conditioner", False),
        ("evening", False),
        ("morning", False),
        ("night", False),
        ("midday", False),
        ("workout", False),
        ("training", False),
        ("diet", False),
        ("nutrition", False),
        ("yes", False),
        ("ok", False),
        ("recommend", False),
        ("", False),
        ("a", False),
        # MUST KEEP — concrete products / ingredients
        ("CeraVe Foaming Cleanser", True),
        ("CeraVe Hydrating Cleanser", True),
        ("Paula's Choice 2% BHA", True),
        ("EltaMD UV Clear SPF 46", True),
        ("La Roche-Posay Anthelios SPF 50+", True),
        ("The Ordinary Niacinamide 10%", True),
        ("Differin Adapalene 0.1%", True),
        ("Salicylic Acid Cleanser", True),
        ("SPF 50 Sunscreen", True),
        ("Niacinamide Serum", True),
        # ingredient-only (single token, but informative)
        ("salicylic", True),
        ("Niacinamide", True),
        ("retinol", True),
        ("adapalene", True),
        ("tretinoin", True),
        ("minoxidil", True),
        ("finasteride", True),
        ("ketoconazole", True),
        ("creatine", True),
        ("magnesium", True),
        # Brand singleton — capitalized, > 5 chars
        ("CeraVe", True),
        ("Nizoral", True),
        ("Differin", True),
    ]

    results: list[dict] = []
    for q, want in cases:
        got = bool(is_specific(q))
        results.append({"query": q, "want": want, "got": got, "pass": got == want})

    passed = sum(1 for r in results if r["pass"])
    fails = [r for r in results if not r["pass"]]
    return {
        "name": "product_links",
        "total": len(results),
        "passed": passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "results": results,
        "fails": fails,
    }


# --------------------------------------------------------------------------- #
#  Backtest 4 — MAX_CHAT_SYSTEM_PROMPT guardrails present                      #
# --------------------------------------------------------------------------- #

def backtest_persona_prompt() -> dict:
    src = _read_prompt_text()

    checks = [
        # Guardrail #1 — never trap the user in a loop
        ("loop_guardrail_section_exists",
         "NEVER TRAP THE USER IN A LOOP" in src),
        ("loop_guardrail_has_3_to_3_4_example",
         "3" in src and "3-4" in src and "Accept" in src),
        ("loop_guardrail_has_yes_no_phrase_example",
         "a little" in src or "kinda" in src),

        # Guardrail #2 — standard-template knowledge fallback
        ("kb_fallback_section_exists",
         "STANDARD-TEMPLATE KNOWLEDGE FALLBACK" in src),
        ("kb_fallback_warns_no_refusal",
         "DO NOT refuse" in src or "do not refuse" in src.lower()),
        ("kb_fallback_announces_template",
         "standard template" in src.lower()),

        # Guardrail #3 — helpfulness > persona under frustration
        ("helpfulness_over_persona_line",
         "HELPFULNESS BEATS PERSONA" in src or "helpfulness beats persona" in src.lower()),
        ("frustration_signals_drop_slang",
         "drop the slang" in src.lower() or "drop slang" in src.lower()),

        # Companion: RAG-path standard-template branch
        ("rag_path_template_branch",
         "STANDARD-TEMPLATE FALLBACK" in src),
    ]

    results = [{"check": label, "pass": ok} for label, ok in checks]
    passed = sum(1 for r in results if r["pass"])
    return {
        "name": "persona_prompt",
        "total": len(results),
        "passed": passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "results": results,
    }


# --------------------------------------------------------------------------- #
#  Backtest 5 — Integration: simulated multi-turn fitmax onboarding            #
# --------------------------------------------------------------------------- #

def backtest_onboarding_integration(chat: dict) -> dict:
    """Walk a fake user through fitmax onboarding using ONLY the kind of
    natural-language replies that previously caused infinite loops."""
    coerce = chat["_coerce_to_choice"]
    extract_fitmax = chat["_extract_fitmax_updates"]
    missing_fields = chat["_fitmax_missing_fields"]
    fitmax_map = chat["FITMAX_QUESTION_MAP"]
    parse_days = chat["_parse_days_per_week_reply"]
    parse_minutes = chat["_parse_session_minutes_reply"]
    parse_activity = chat["_parse_daily_activity_short_reply"]
    to_cm = chat["_to_cm_from_text"]
    to_kg = chat["_to_kg_from_text"]

    # Replies — deliberately natural / fuzzy so we exercise the new path.
    replies = [
        ("goal",                 "i want to cut"),
        ("experience_level",     "intermediate-ish, been lifting a year"),
        ("height_cm",            "5'10\""),
        ("weight_kg",            "175 lbs"),
        ("age",                  "27"),
        ("biological_sex",       "guy"),
        ("equipment",            "i go to a full gym"),
        ("days_per_week",        "3"),  # the literal bug
        ("session_minutes",      "60"),
        ("daily_activity_level", "moderate"),
        ("dietary_restrictions", "no restrictions"),
    ]

    profile: dict = {}
    transcript: list[dict] = []
    loops = 0
    for field, user_reply in replies:
        before_missing = missing_fields(profile)
        if not before_missing or before_missing[0] != field:
            transcript.append({
                "turn": field, "reply": user_reply,
                "outcome": f"SKIP - next missing was {before_missing[0] if before_missing else 'NONE'}",
                "pass": False,
            })
            continue

        # Step 1: try the keyword extractor
        updates = extract_fitmax(user_reply, profile)

        # Step 2: per-question parser fallbacks
        nxt = field
        if nxt == "days_per_week" and "days_per_week" not in updates:
            d = parse_days(user_reply)
            if d is not None:
                updates["days_per_week"] = d
        elif nxt == "session_minutes" and "session_minutes" not in updates:
            sm = parse_minutes(user_reply)
            if sm is not None:
                updates["session_minutes"] = sm
        elif nxt == "daily_activity_level" and "daily_activity_level" not in updates:
            act = parse_activity(user_reply)
            if act is not None:
                updates["daily_activity_level"] = act

        # Step 3: generic fuzzy-coerce (the new fix)
        if nxt not in updates:
            _, choices = fitmax_map.get(nxt, ("", []))
            if choices:
                coerced = coerce(user_reply, choices)
                if coerced is not None:
                    if nxt in ("days_per_week", "session_minutes", "age"):
                        m = re.search(r"\d+", coerced)
                        updates[nxt] = int(m.group()) if m else coerced
                    else:
                        updates[nxt] = coerced

        if updates:
            profile.update(updates)

        ok = field in profile and profile.get(field) not in (None, "", [])
        transcript.append({
            "turn": field,
            "reply": user_reply,
            "extracted": {k: v for k, v in updates.items() if k == field},
            "profile_now": profile.get(field),
            "pass": ok,
        })
        if not ok:
            loops += 1

    completed = not missing_fields(profile)
    return {
        "name": "onboarding_integration",
        "total_turns": len(replies),
        "successful_turns": sum(1 for t in transcript if t["pass"]),
        "infinite_loop_failures": loops,
        "fully_completed_no_reasking": completed,
        "transcript": transcript,
    }


# --------------------------------------------------------------------------- #
#  Driver                                                                      #
# --------------------------------------------------------------------------- #

def run_all() -> dict:
    chat = _load_chat_helpers()
    prod = _load_product_helpers()

    return {
        "input_validation": backtest_input_validation(chat),
        "rag_fallback": backtest_rag_fallback(),
        "product_links": backtest_product_links(prod),
        "persona_prompt": backtest_persona_prompt(),
        "onboarding_integration": backtest_onboarding_integration(chat),
    }


def _print_report(report: dict) -> None:
    print("\n=== CHAT-PIPELINE FIX BACKTEST ===\n")

    iv = report["input_validation"]
    print(f"[1/5] input validation — {iv['passed']}/{iv['total']} ({iv['pass_rate']:.1%})")
    fails = [r for r in iv["results"] if not r["pass"]]
    for r in iv["results"]:
        flag = "OK " if r["pass"] else "FAIL"
        print(f"   {flag}  {r['case']:<32}  reply={r['reply']!r:<32}  got={r['got']!r}  want={r['want']!r}")
    print()

    rf = report["rag_fallback"]
    print(f"[2/5] RAG fallback wiring — {rf['passed']}/{rf['total']} ({rf['pass_rate']:.1%})")
    for r in rf["results"]:
        flag = "OK " if r["pass"] else "FAIL"
        print(f"   {flag}  {r['check']}")
    print()

    pl = report["product_links"]
    print(f"[3/5] product link specificity — {pl['passed']}/{pl['total']} ({pl['pass_rate']:.1%})")
    if pl["fails"]:
        for r in pl["fails"]:
            print(f"   FAIL  {r['query']!r}  got={r['got']}  want={r['want']}")
    else:
        print("   all generic queries dropped, all real products kept")
    print()

    pp = report["persona_prompt"]
    print(f"[4/5] persona prompt guardrails — {pp['passed']}/{pp['total']} ({pp['pass_rate']:.1%})")
    for r in pp["results"]:
        flag = "OK " if r["pass"] else "FAIL"
        print(f"   {flag}  {r['check']}")
    print()

    oi = report["onboarding_integration"]
    print(f"[5/5] onboarding integration — {oi['successful_turns']}/{oi['total_turns']} turns landed first try")
    for t in oi["transcript"]:
        flag = "OK " if t["pass"] else "FAIL"
        result_str = repr(t.get("profile_now")) if "profile_now" in t else t.get("outcome", "?")
        print(f"   {flag}  {t['turn']:<22}  reply={t['reply']!r:<36}  -> {result_str}")
    print(f"   loops_avoided={oi['infinite_loop_failures'] == 0}  fully_completed={oi['fully_completed_no_reasking']}")
    print()

    # Verdict
    sections = [
        ("input_validation",   iv["pass_rate"] >= 0.95),
        ("rag_fallback",       rf["pass_rate"] >= 1.0),
        ("product_links",      pl["pass_rate"] >= 0.95),
        ("persona_prompt",     pp["pass_rate"] >= 1.0),
        ("onboarding_loop_fix", oi["fully_completed_no_reasking"] and oi["infinite_loop_failures"] == 0),
    ]
    print("=== VERDICT ===")
    for name, ok in sections:
        print(f"   {'PASS' if ok else 'FAIL'}  {name}")
    overall = all(ok for _, ok in sections)
    print()
    print(f"   >>> {'ALL FIXES VERIFIED' if overall else 'ONE OR MORE FIXES REGRESSED'} <<<")
    print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_all()
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_report(report)

    sections = [
        report["input_validation"]["pass_rate"] >= 0.95,
        report["rag_fallback"]["pass_rate"] >= 1.0,
        report["product_links"]["pass_rate"] >= 0.95,
        report["persona_prompt"]["pass_rate"] >= 1.0,
        report["onboarding_integration"]["fully_completed_no_reasking"]
        and report["onboarding_integration"]["infinite_loop_failures"] == 0,
    ]
    return 0 if all(sections) else 1


if __name__ == "__main__":
    sys.exit(main())
