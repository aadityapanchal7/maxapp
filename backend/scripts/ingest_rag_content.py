"""Bulk-load per-topic markdowns from `rag_content/{maxx}/*.md` into the
Supabase `rag_documents` table.

Why a second ingest path: `ingest_max_docs.py` consumes the whole-module
spec files at `data/maxes/*.md`. This script consumes the per-topic
coaching MDs (one topic per file) that we author when growing the
knowledge base for a maxx — e.g. the bonemax + fitmax doc carve-up.

For each file:
  - `maxx_id`   = parent dir name
  - `doc_title` = file stem (e.g. "foundations", "jawline")
  - `content`   = full file text
  - `embedding` = OpenAI embedding of `(doc_title \\n\\n content)`
  - `metadata`  = {section: doc_title, source: rag_content/{maxx}/{file}}

Idempotent: deletes prior rows whose `metadata->>'source'` starts with
`rag_content/{maxx}/`, then re-inserts. Other rows for the maxx (e.g.
spec-doc chunks ingested by `ingest_max_docs.py`) are left alone.

Run:
    python -m backend.scripts.ingest_rag_content                        # all maxxes
    python -m backend.scripts.ingest_rag_content --maxx bonemax fitmax  # selected
    python -m backend.scripts.ingest_rag_content --dry-run              # parse only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text  # noqa: E402

from db.sqlalchemy import AsyncSessionLocal  # noqa: E402
from services.rag_service import (  # noqa: E402
    VALID_MAXX_IDS,
    _vec_to_pg_str,
    embed_batch,
    reload_indexes,
)

logger = logging.getLogger("ingest_rag_content")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

RAG_CONTENT_DIR = Path(__file__).resolve().parent.parent / "rag_content"


def _iter_files(maxx_filter: list[str] | None) -> list[tuple[str, Path]]:
    """Yield (maxx_id, path) for every `.md` under rag_content/."""
    out: list[tuple[str, Path]] = []
    if not RAG_CONTENT_DIR.is_dir():
        raise SystemExit(f"rag_content dir not found at {RAG_CONTENT_DIR}")
    for maxx_dir in sorted(p for p in RAG_CONTENT_DIR.iterdir() if p.is_dir()):
        maxx_id = maxx_dir.name
        if maxx_id not in VALID_MAXX_IDS:
            logger.warning("skipping unknown maxx dir: %s", maxx_id)
            continue
        if maxx_filter and maxx_id not in maxx_filter:
            continue
        for md in sorted(maxx_dir.glob("*.md")):
            out.append((maxx_id, md))
    return out


async def _ingest_maxx(session, maxx_id: str, files: list[Path]) -> int:
    """Replace `rag_content/{maxx}/*` rows in rag_documents for one module.

    Files outside this prefix (e.g. spec-doc chunks ingested by
    ingest_max_docs.py) are preserved. The metadata.source filter is the
    only thing that distinguishes them.
    """
    # Wipe prior per-topic rows for this maxx, leave spec-doc rows alone.
    await session.execute(
        text(
            """
            DELETE FROM rag_documents
            WHERE maxx_id = :mid
              AND metadata->>'source' LIKE :prefix
            """
        ),
        {"mid": maxx_id, "prefix": f"rag_content/{maxx_id}/%"},
    )

    if not files:
        return 0

    # Embed everything in one batch — one network round trip per maxx.
    bodies = []
    titles = []
    for f in files:
        body = f.read_text(encoding="utf-8").strip()
        if not body:
            continue
        bodies.append(body)
        titles.append(f.stem)

    try:
        # Embed `(title \n\n body)` so the section context is in the vector.
        embeddings = await embed_batch([f"{t}\n\n{b}" for t, b in zip(titles, bodies)])
    except Exception as e:
        logger.warning("embedding failed for %s, ingesting without vectors: %s", maxx_id, e)
        embeddings = []

    n = 0
    for i, (title, body) in enumerate(zip(titles, bodies)):
        emb = embeddings[i] if i < len(embeddings) else None
        emb_lit = _vec_to_pg_str(emb) if emb else None
        params = {
            "maxx_id": maxx_id,
            "doc_title": title,
            "chunk_index": 0,  # whole-file row; chunker re-splits at index time
            "content": body,
            "metadata": json.dumps({
                "section": title,
                "source": f"rag_content/{maxx_id}/{title}.md",
            }),
            "embedding": emb_lit,
        }
        if emb_lit:
            sql = text(
                """
                INSERT INTO rag_documents
                  (maxx_id, doc_title, chunk_index, content, metadata, embedding)
                VALUES
                  (:maxx_id, :doc_title, :chunk_index, :content,
                   CAST(:metadata AS jsonb), CAST(:embedding AS vector))
                """
            )
        else:
            sql = text(
                """
                INSERT INTO rag_documents
                  (maxx_id, doc_title, chunk_index, content, metadata)
                VALUES
                  (:maxx_id, :doc_title, :chunk_index, :content,
                   CAST(:metadata AS jsonb))
                """
            )
            params.pop("embedding")
        await session.execute(sql, params)
        n += 1
    return n


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--maxx",
        nargs="*",
        default=None,
        help="Restrict to one or more maxx_ids (default: all)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    args = parser.parse_args()

    files = _iter_files(args.maxx)
    if not files:
        print("No matching markdown files found under rag_content/")
        return 1

    by_maxx: dict[str, list[Path]] = {}
    for maxx_id, p in files:
        by_maxx.setdefault(maxx_id, []).append(p)

    print(f"Found {len(files)} markdown file(s) across {len(by_maxx)} maxx(es):")
    for m, fs in by_maxx.items():
        print(f"  - {m:>12}: {len(fs)} files")

    if args.dry_run:
        print("\n--dry-run: no DB writes")
        return 0

    print("\nIngesting...")
    results: list[tuple[str, int, int]] = []
    for maxx_id, fs in by_maxx.items():
        t0 = time.perf_counter()
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    n = await _ingest_maxx(session, maxx_id, fs)
            results.append((maxx_id, n, int((time.perf_counter() - t0) * 1000)))
            print(f"  [ok ] {maxx_id:>12}: {n} rows ({results[-1][2]}ms)")
        except Exception as e:
            logger.exception("ingest failed for %s: %s", maxx_id, e)
            results.append((maxx_id, -1, 0))
            print(f"  [FAIL] {maxx_id:>12}: {e}")

    # Refresh in-memory BM25 caches so the next chat turn sees the new content.
    try:
        reload_indexes()
        print("\nIn-memory BM25 caches cleared. Next KNOWLEDGE turn re-loads.")
    except Exception as e:
        logger.warning("reload_indexes failed (non-fatal): %s", e)

    failed = [r for r in results if r[1] < 0]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
