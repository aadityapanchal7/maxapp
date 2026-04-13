"""Run retrieval evals against the seeded kb_chunks.

Measures: for each question, did we retrieve at least one chunk from the expected
module, and did any retrieved chunk contain the expected keywords?

Usage:
    python -m backend.scripts.run_evals
    python -m backend.scripts.run_evals --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from db.sqlalchemy import AsyncSessionLocal, engine  # noqa: E402
from services.rag_service import retrieve  # noqa: E402


async def run(verbose: bool = False) -> dict:
    evals_path = REPO_ROOT / "backend" / "evals" / "questions.jsonl"
    cases = [json.loads(l) for l in evals_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    module_hits = 0
    keyword_hits = 0
    any_chunk = 0

    async with AsyncSessionLocal() as db:
        for case in cases:
            q = case["question"]
            chunks = await retrieve(db, q)
            any_chunk += 1 if chunks else 0
            got_module = any(c.module == case.get("expected_module") for c in chunks)
            joined = " ".join(c.content.lower() for c in chunks)
            got_kw = all(kw.lower() in joined for kw in (case.get("expected_keywords") or []))
            module_hits += 1 if got_module else 0
            keyword_hits += 1 if got_kw else 0
            if verbose:
                print(f"\nQ: {q}")
                print(f"   module_match={got_module} keyword_match={got_kw} chunks={len(chunks)}")
                for c in chunks[:2]:
                    print(f"   - [{c.module} score={c.score:.2f}] {c.content[:120]}...")

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
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
