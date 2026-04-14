"""Smoke test the fast retrieval + answer path without DB state.

Usage:
    python scripts/test_fast_rag.py "what products help red skin" --maxx skinmax
    python scripts/test_fast_rag.py "what is mewing" --maxx bonemax
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fast_rag_answer import answer_from_rag


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("message")
    parser.add_argument("--maxx", action="append", default=[])
    args = parser.parse_args()

    t0 = time.perf_counter()
    answer, chunks = await answer_from_rag(
        message=args.message,
        maxx_hints=list(args.maxx or []),
    )
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    print(f"\n>>> {args.message}\n")
    print(f"<<< {answer or '[no answer]'}\n")
    print(f"[chunks={len(chunks)} elapsed_ms={elapsed_ms}]")
    for chunk in chunks:
        meta = chunk.get("metadata") or {}
        print(
            f"- {meta.get('source') or '?'} | {meta.get('section') or '?'} "
            f"| sim={chunk.get('similarity')}"
        )


if __name__ == "__main__":
    asyncio.run(main())
