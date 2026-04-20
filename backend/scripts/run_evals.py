"""Run retrieval evals against the live file-based BM25 retriever."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from config import settings  # noqa: E402
from services.rag_service import retrieve_chunks  # noqa: E402


async def run(verbose: bool = False) -> dict:
    evals_path = REPO_ROOT / "backend" / "evals" / "questions.jsonl"
    cases = [json.loads(l) for l in evals_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    module_hits = 0
    keyword_hits = 0
    any_chunk = 0

    for case in cases:
        q = case["question"]
        module = case.get("expected_module")
        chunks = await retrieve_chunks(
            None,
            maxx_id=module,
            query=q,
            k=int(getattr(settings, "rag_top_k", 4) or 4),
            min_similarity=float(getattr(settings, "rag_score_threshold", 0.35) or 0.35),
        )
        any_chunk += 1 if chunks else 0
        got_module = bool(chunks)
        joined = " ".join(c.get("content", "").lower() for c in chunks)
        got_kw = all(kw.lower() in joined for kw in (case.get("expected_keywords") or []))
        module_hits += 1 if got_module else 0
        keyword_hits += 1 if got_kw else 0
        if verbose:
            print(f"\nQ: {q}")
            print(f"   module_match={got_module} keyword_match={got_kw} chunks={len(chunks)}")
            for c in chunks[:2]:
                meta = c.get("metadata") or {}
                print(
                    f"   - [{module} score={c.get('similarity', 0):.2f}] "
                    f"{meta.get('source') or '?'} :: {c.get('content', '')[:120]}..."
                )

    n = len(cases) or 1
    summary = {
        "cases": n,
        "retrieval_rate": any_chunk / n,
        "module_hit_rate": module_hits / n,
        "keyword_hit_rate": keyword_hits / n,
    }
    print("\n=== EVAL SUMMARY ===")
    for k, v in summary.items():
        print(f"{k}: {v}")
    return summary


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    await run(verbose=args.verbose)


if __name__ == "__main__":
    asyncio.run(main())
