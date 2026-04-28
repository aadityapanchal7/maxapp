"""Backtest RAG retrieval correctness + latency without needing the live DB.

Loads the same docs that `seed_rag_organized.py` writes to Supabase, builds the
exact in-memory BM25 indexes the runtime uses, and runs a labeled query mix
against them. Reports per-module accuracy, top-3 recall, latency, and the
fraction of top-k hits that come from real-content docs vs stub placeholders.

Usage:
    python scripts/bench_rag_retrieval.py
    python scripts/bench_rag_retrieval.py --json   # machine-readable
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_ROOT))

from scripts.seed_rag_organized import DOCS  # source of truth for what's in DB
from services.rag_service import _Bm25Index, _split_markdown_with_headings, _chunk_id
from services.intent_classifier import classify_turn
from services.rag_prompt_selector import _LEXICONS, select_rag_system_prompt
from services import prompt_loader


# --------------------------------------------------------------------------- #
#  Build BM25 indexes from the seed (mirrors rag_service._load_maxx_index)    #
# --------------------------------------------------------------------------- #

def _build_index(maxx_id: str, docs_for_maxx: list[dict]) -> _Bm25Index:
    chunks: list[dict] = []
    for doc in docs_for_maxx:
        body = doc["content"]
        doc_title = doc["doc_title"]
        source_path = f"rag_documents/{maxx_id}/{doc_title}"
        for block in _split_markdown_with_headings(body):
            section = block["section"] or doc_title
            content = block["content"]
            search_text = "\n".join(p for p in (doc_title, section, content) if p)
            chunks.append({
                "id": _chunk_id(
                    source=source_path,
                    doc_title=doc_title,
                    section=section,
                    chunk_index=int(block["chunk_index"]),
                ),
                "content": content,
                "search_text": search_text,
                "doc_title": doc_title,
                "chunk_index": int(block["chunk_index"]),
                "priority_boost": 1.0,
                "metadata": {
                    "source": source_path,
                    "section": section,
                    # Tag whether this came from a real-content doc or a stub
                    # so the benchmark can count quality, not just hits.
                    "is_stub": len(body) < 500,
                },
            })
    return _Bm25Index(chunks)


def _build_all_indexes() -> dict[str, _Bm25Index]:
    by_maxx: dict[str, list[dict]] = defaultdict(list)
    for doc in DOCS:
        by_maxx[doc["maxx_id"]].append(doc)
    return {m: _build_index(m, docs) for m, docs in by_maxx.items()}


def _is_stub_doc(maxx_id: str, doc_title: str) -> bool:
    for d in DOCS:
        if d["maxx_id"] == maxx_id and d["doc_title"] == doc_title:
            return len(d["content"]) < 500
    return True


# Mirror of services.fast_rag_answer._expand_query, inlined here so the bench
# stays free of langchain deps. Keep this in sync with the production version.
_EXPANSION_TERMS: dict[str, list[str]] = {
    maxx: [t for t, w in lex.items() if w >= 3 and " " not in t]
    for maxx, lex in _LEXICONS.items()
}


def _expand_query(query: str, maxx: str) -> str:
    """Mirror of fast_rag_answer._expand_query — fallback expansion only."""
    if len(query.split()) >= 8:
        return query
    expansion = _EXPANSION_TERMS.get(maxx, [])
    if not expansion:
        return query
    q_lower = query.lower()
    extras = [t for t in expansion[:6] if t not in q_lower]
    if not extras:
        return query
    return f"{query} {' '.join(extras)}"


# --------------------------------------------------------------------------- #
#  Labeled query mix — covers the cases the user complained about             #
# --------------------------------------------------------------------------- #

# (query, expected_maxx, expected_doc_title)
# expected_doc_title can be None when the *module* is what matters; we'll still
# score top-1 doc match for telemetry.
QUERY_MIX: list[tuple[str, str, str | None]] = [
    # bonemax — including the slang the user explicitly called out
    ("how do i bonesmash my zygomatic", "bonemax", None),
    ("bonesmashing routine for jawline", "bonemax", None),
    ("looksmaxxing protocol for psl gain", "bonemax", None),
    ("what is mewing exactly", "bonemax", "Mewing"),
    ("hard mewing vs soft mewing", "bonemax", "Mewing"),
    ("how long until mastic gum changes jawline", "bonemax", "Jaw Exercises"),
    ("tmj from chewing too hard", "bonemax", "Jaw Exercises"),
    ("falim gum daily safe", "bonemax", "Jaw Exercises"),
    ("calcium and k2 for jaw bone density", "bonemax", "Bone Density & Diet"),
    ("orthotropics maxilla forward growth", "bonemax", "Facial Structure"),
    ("bilateral chewing technique", "bonemax", "Chewing Protocol"),

    # skinmax — including debloating, the other named topic
    ("debloating my puffy face fast", "skinmax", "Debloat"),
    ("how to debloat before a date", "skinmax", "Debloat"),
    ("water retention in my face this morning", "skinmax", "Debloat"),
    ("ice roller for puffy face", "skinmax", "Debloat"),
    ("what should i do for acne at night", "skinmax", "Acne"),
    ("adapalene safe daily", "skinmax", "Acne"),
    ("am pm routine order", "skinmax", "Routines"),
    ("chemical vs mineral sunscreen", "skinmax", "Sun Protection"),
    ("retinoids and collagen anti aging", "skinmax", "Anti-Aging"),

    # hairmax
    ("how often should i apply minoxidil", "hairmax", "Minoxidil"),
    ("does finasteride actually regrow hair", "hairmax", "Finasteride"),
    ("dht blockers explained", "hairmax", "Finasteride"),
    ("dermaroller depth for hair growth", "hairmax", "Dermarolling"),
    ("scalp ketoconazole shampoo schedule", "hairmax", "Scalp Health"),
    ("am i nw2 or nw3", "hairmax", None),

    # heightmax
    ("forward head posture fix", "heightmax", "Posture"),
    ("hanging from pullup bar daily", "heightmax", "Spinal Decompression"),
    ("growth hormone deep sleep", "heightmax", "Sleep & Growth"),
    ("calcium d3 for taller", "heightmax", "Nutrition for Height"),
    ("hip flexor stretch routine", "heightmax", "Stretching"),

    # fitmax
    ("how to cut for summer", "fitmax", "Cutting"),
    ("ppl vs upper lower split", "fitmax", "Training Split"),
    ("macro split for lean bulk", "fitmax", "Leaning Out & Macros"),
    ("creatine timing on rest days", "fitmax", "Supplements"),
    ("ideal shoulder to waist ratio", "fitmax", "Bodily Dimensions"),

    # Hard-mode bare slang (fallback expansion test) — these are 1-2 word
    # queries with no protocol-anchor terms; they should still return SOMETHING
    # from the right module via the expansion fallback.
    ("looksmaxxing", "bonemax", None),
    ("bonesmash", "bonemax", None),
    ("debloat", "skinmax", "Debloat"),
    ("nw3", "hairmax", None),
    ("psl", "bonemax", None),
]


# --------------------------------------------------------------------------- #
#  Bench                                                                       #
# --------------------------------------------------------------------------- #

def run_benchmark(*, k: int = 4, min_score: float = 0.35, expand: bool = False) -> dict:
    indexes = _build_all_indexes()
    # Seed prompt cache so selector returns deterministic results. We seed
    # both protocol_reference (preferred) and coaching_reference (legacy) so
    # the bench works pre- and post-supabase-seed.
    prompt_loader._CACHE.update({
        prompt_loader.PromptKey.RAG_ANSWER_SYSTEM: "BASE",
        "skinmax_protocol_reference": "SKINMAX REF",
        "fitmax_protocol_reference": "FITMAX REF",
        "hairmax_protocol_reference": "HAIRMAX REF",
        "bonemax_protocol_reference": "BONEMAX REF",
        "heightmax_protocol_reference": "HEIGHTMAX REF",
    })

    expander = _expand_query if expand else None

    # Pre-warm so the timing samples are warm-path numbers.
    for idx in indexes.values():
        idx.top_k("warmup", k=1, min_score=0.0)

    per_module_total: Counter = Counter()
    module_route_correct: Counter = Counter()
    doc_top1_correct: Counter = Counter()
    doc_top3_correct: Counter = Counter()
    stub_top1: Counter = Counter()  # count of top-1 hits that landed on stubs
    real_top1: Counter = Counter()
    no_results: list[str] = []
    misses: list[dict] = []
    latencies_ms: list[float] = []

    for query, expected_maxx, expected_doc in QUERY_MIX:
        per_module_total[expected_maxx] += 1

        # Step 1: classifier → maxx hint
        intent = classify_turn(query)
        hints = intent.get("maxx_hints") or []
        # Step 2: selector decides which index to use (mirrors fast_rag_answer)
        selection = select_rag_system_prompt(query, maxx_hints=hints)
        chosen_maxx = selection.chosen_maxx or (hints[0] if hints else None)
        if chosen_maxx == expected_maxx:
            module_route_correct[expected_maxx] += 1

        # Step 3: retrieve from chosen index (or expected one if router failed,
        # so doc-level metric isolates content quality from routing failure)
        retrieval_maxx = chosen_maxx or expected_maxx
        idx = indexes.get(retrieval_maxx)
        if idx is None:
            no_results.append(query)
            misses.append({"query": query, "reason": "no_index", "chosen": retrieval_maxx})
            continue

        # Mirror fast_rag_answer's two-pass model: try original query first;
        # only fall back to expansion if first pass returned nothing.
        t0 = time.perf_counter()
        rows = idx.top_k(query, k=k, min_score=min_score)
        if not rows and expander:
            expanded = expander(query, retrieval_maxx)
            if expanded != query:
                rows = idx.top_k(expanded, k=k, min_score=min_score)
        latencies_ms.append((time.perf_counter() - t0) * 1000)

        if not rows:
            no_results.append(query)
            misses.append({"query": query, "reason": "no_chunks", "chosen": retrieval_maxx})
            continue

        top1_doc = rows[0]["doc_title"]
        top1_is_stub = bool(rows[0]["metadata"].get("is_stub"))
        if top1_is_stub:
            stub_top1[expected_maxx] += 1
        else:
            real_top1[expected_maxx] += 1

        if expected_doc and top1_doc == expected_doc:
            doc_top1_correct[expected_maxx] += 1
        if expected_doc and any(r["doc_title"] == expected_doc for r in rows[:3]):
            doc_top3_correct[expected_maxx] += 1
        if expected_doc and top1_doc != expected_doc:
            misses.append({
                "query": query,
                "expected_doc": expected_doc,
                "got_doc": top1_doc,
                "score": rows[0]["similarity"],
                "is_stub": top1_is_stub,
            })

    # Aggregate
    total = sum(per_module_total.values())
    module_acc = {
        m: (module_route_correct[m] / per_module_total[m]) if per_module_total[m] else 0.0
        for m in per_module_total
    }
    # doc-level metrics only counted on queries that had an expected_doc
    doc_eligible_per_module: Counter = Counter()
    for q, em, ed in QUERY_MIX:
        if ed:
            doc_eligible_per_module[em] += 1

    doc_top1_acc = {
        m: (doc_top1_correct[m] / doc_eligible_per_module[m]) if doc_eligible_per_module[m] else 0.0
        for m in doc_eligible_per_module
    }
    doc_top3_acc = {
        m: (doc_top3_correct[m] / doc_eligible_per_module[m]) if doc_eligible_per_module[m] else 0.0
        for m in doc_eligible_per_module
    }
    real_share = {
        m: (real_top1[m] / per_module_total[m]) if per_module_total[m] else 0.0
        for m in per_module_total
    }

    overall = {
        "queries": total,
        "module_route_acc": sum(module_route_correct.values()) / max(1, total),
        "doc_top1_acc": (
            sum(doc_top1_correct.values()) / max(1, sum(doc_eligible_per_module.values()))
        ),
        "doc_top3_acc": (
            sum(doc_top3_correct.values()) / max(1, sum(doc_eligible_per_module.values()))
        ),
        "real_top1_share": sum(real_top1.values()) / max(1, total),
        "stub_top1_share": sum(stub_top1.values()) / max(1, total),
        "no_results_count": len(no_results),
        "latency_p50_ms": round(statistics.median(latencies_ms), 3) if latencies_ms else 0.0,
        "latency_p95_ms": round(
            sorted(latencies_ms)[int(0.95 * len(latencies_ms))] if latencies_ms else 0.0, 3
        ),
        "latency_max_ms": round(max(latencies_ms), 3) if latencies_ms else 0.0,
    }

    return {
        "overall": overall,
        "per_module": {
            m: {
                "queries": per_module_total[m],
                "module_route_acc": round(module_acc[m], 3),
                "doc_top1_acc": round(doc_top1_acc.get(m, 0.0), 3),
                "doc_top3_acc": round(doc_top3_acc.get(m, 0.0), 3),
                "real_top1_share": round(real_share[m], 3),
                "stub_top1_count": stub_top1[m],
            }
            for m in per_module_total
        },
        "misses_top10": misses[:10],
    }


def _print_report(r: dict) -> None:
    o = r["overall"]
    print("\n=== RAG RETRIEVAL BACKTEST ===")
    print(f"  queries            : {o['queries']}")
    print(f"  module routing acc : {o['module_route_acc']:.1%}")
    print(f"  doc top-1 acc      : {o['doc_top1_acc']:.1%}")
    print(f"  doc top-3 acc      : {o['doc_top3_acc']:.1%}")
    print(f"  real-content top-1 : {o['real_top1_share']:.1%}  (rest land on stub placeholders)")
    print(f"  stub top-1 share   : {o['stub_top1_share']:.1%}  <-- content gap")
    print(f"  no-result queries  : {o['no_results_count']}")
    print(f"  latency p50/p95/max: {o['latency_p50_ms']:.2f} / {o['latency_p95_ms']:.2f} / {o['latency_max_ms']:.2f} ms")
    print("\n  per-module:")
    print(f"    {'module':<10} {'n':>3}  {'route':>6}  {'top1':>6}  {'top3':>6}  {'real':>6}  {'stubs':>6}")
    for m, s in sorted(r["per_module"].items()):
        print(
            f"    {m:<10} {s['queries']:>3}  "
            f"{s['module_route_acc']:>6.0%}  "
            f"{s['doc_top1_acc']:>6.0%}  "
            f"{s['doc_top3_acc']:>6.0%}  "
            f"{s['real_top1_share']:>6.0%}  "
            f"{s['stub_top1_count']:>6}"
        )

    if r["misses_top10"]:
        print("\n  first misses:")
        for m in r["misses_top10"]:
            if "expected_doc" in m:
                stub = " (STUB)" if m.get("is_stub") else ""
                print(
                    f"    expected={m['expected_doc']:<22} "
                    f"got={m['got_doc']:<22}{stub}  "
                    f"score={m.get('score', 0):.2f}  q={m['query']!r}"
                )
            else:
                print(f"    [{m['reason']}] chosen={m['chosen']}  q={m['query']!r}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="output JSON only")
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--min-score", type=float, default=0.35)
    parser.add_argument(
        "--compare", action="store_true",
        help="run both expansion off and on, print A/B side-by-side"
    )
    parser.add_argument(
        "--expand", action="store_true",
        help="enable query expansion via _expand_query"
    )
    args = parser.parse_args()

    if args.compare:
        baseline = run_benchmark(k=args.k, min_score=args.min_score, expand=False)
        with_expand = run_benchmark(k=args.k, min_score=args.min_score, expand=True)
        if args.json:
            print(json.dumps({"baseline": baseline, "with_expansion": with_expand}, indent=2))
        else:
            print("\n--- A: BASELINE (no expansion) ---")
            _print_report(baseline)
            print("--- B: WITH QUERY EXPANSION ---")
            _print_report(with_expand)
            ob, oe = baseline["overall"], with_expand["overall"]
            print("=== A vs B ===")
            print(f"  doc_top1_acc        : {ob['doc_top1_acc']:.1%} -> {oe['doc_top1_acc']:.1%}")
            print(f"  doc_top3_acc        : {ob['doc_top3_acc']:.1%} -> {oe['doc_top3_acc']:.1%}")
            print(f"  real_top1_share     : {ob['real_top1_share']:.1%} -> {oe['real_top1_share']:.1%}")
            print(f"  no_results_count    : {ob['no_results_count']} -> {oe['no_results_count']}")
            print(f"  latency p50_ms      : {ob['latency_p50_ms']:.2f} -> {oe['latency_p50_ms']:.2f}")
            print()
        return

    report = run_benchmark(k=args.k, min_score=args.min_score, expand=args.expand)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)


if __name__ == "__main__":
    main()
