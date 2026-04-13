"""Ingest course content (CSV or the existing maxx_guidelines constants) into kb_chunks.

Usage:
    python -m backend.scripts.ingest_kb --csv path/to/course.csv
    python -m backend.scripts.ingest_kb --seed-guidelines  # pulls from maxx_guidelines.py

CSV schema (flexible; missing columns default):
    module,persona,content
Anything else in the row is stuffed into `metadata` as JSON.

Re-running is idempotent — rows are keyed by SHA-256 of normalized content.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# Make `backend/` importable when running via `python -m` from repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import text as sa_text  # noqa: E402

from db.sqlalchemy import AsyncSessionLocal, engine  # noqa: E402
from services.embedding_service import embed_texts  # noqa: E402


CHUNK_TARGET_CHARS = 1600  # ~400 tokens; keeps each chunk focused
CHUNK_OVERLAP_CHARS = 200


def _normalize(s: str) -> str:
    return " ".join((s or "").split()).strip()


def _hash(content: str) -> str:
    return hashlib.sha256(_normalize(content).encode("utf-8")).hexdigest()


def _split(content: str) -> List[str]:
    """Paragraph-aware splitter. For course rows that are already short, returns [content]."""
    c = content.strip()
    if len(c) <= CHUNK_TARGET_CHARS:
        return [c] if c else []
    parts: List[str] = []
    start = 0
    while start < len(c):
        end = min(start + CHUNK_TARGET_CHARS, len(c))
        # Prefer splitting at a paragraph / sentence boundary.
        if end < len(c):
            boundary = c.rfind("\n\n", start, end)
            if boundary == -1:
                boundary = c.rfind(". ", start, end)
            if boundary != -1 and boundary > start + 200:
                end = boundary + 1
        parts.append(c[start:end].strip())
        if end >= len(c):
            break
        start = max(end - CHUNK_OVERLAP_CHARS, start + 1)
    return [p for p in parts if p]


def _rows_from_csv(csv_path: Path) -> Iterable[Tuple[str, Optional[str], str, dict]]:
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            module = (row.get("module") or row.get("Module") or "general").strip() or "general"
            persona = (row.get("persona") or None) or None
            content = (row.get("content") or row.get("Content") or "").strip()
            if not content:
                continue
            meta = {
                k: v for k, v in row.items()
                if k not in ("module", "Module", "persona", "content", "Content") and v
            }
            yield module, persona, content, meta


def _rows_from_guidelines() -> Iterable[Tuple[str, Optional[str], str, dict]]:
    """Pull the existing SKINMAX_PROTOCOLS + any module strings as initial RAG seed."""
    try:
        from services.maxx_guidelines import SKINMAX_PROTOCOLS  # type: ignore
    except Exception as e:
        print(f"[warn] couldn't import maxx_guidelines: {e}")
        return
    for concern_id, body in (SKINMAX_PROTOCOLS or {}).items():
        if isinstance(body, str) and body.strip():
            yield "skinmax", None, body.strip(), {"skin_concern": concern_id}


async def _existing_hashes(session) -> set[str]:
    res = await session.execute(sa_text("SELECT content_hash FROM kb_chunks"))
    return {r[0] for r in res.fetchall()}


async def ingest(
    rows: Iterable[Tuple[str, Optional[str], str, dict]],
    *,
    batch_size: int = 64,
) -> dict:
    inserted = 0
    skipped_existing = 0
    skipped_empty = 0

    async with AsyncSessionLocal() as session:
        existing = await _existing_hashes(session)

        pending: List[Tuple[str, Optional[str], str, str, dict]] = []  # (module, persona, chunk, hash, meta)
        for module, persona, content, meta in rows:
            for chunk in _split(content):
                if not chunk:
                    skipped_empty += 1
                    continue
                h = _hash(chunk)
                if h in existing:
                    skipped_existing += 1
                    continue
                existing.add(h)
                pending.append((module, persona, chunk, h, meta))

        if not pending:
            print(f"[ingest] nothing to insert (skipped existing={skipped_existing}, empty={skipped_empty})")
            return {"inserted": 0, "skipped_existing": skipped_existing, "skipped_empty": skipped_empty}

        for i in range(0, len(pending), batch_size):
            batch = pending[i : i + batch_size]
            texts = [b[2] for b in batch]
            print(f"[ingest] embedding batch {i // batch_size + 1} ({len(batch)} chunks)...")
            vectors = await embed_texts(texts)

            for (module, persona, chunk, h, meta), vec in zip(batch, vectors):
                vec_literal = "[" + ",".join(f"{float(x):.7f}" for x in vec) + "]"
                await session.execute(
                    sa_text(
                        """
                        INSERT INTO kb_chunks (module, persona, content, content_hash, embedding, metadata)
                        VALUES (:module, :persona, :content, :hash, (:vec)::vector, :meta)
                        ON CONFLICT (content_hash) DO NOTHING
                        """
                    ),
                    {
                        "module": module,
                        "persona": persona,
                        "content": chunk,
                        "hash": h,
                        "vec": vec_literal,
                        "meta": json.dumps(meta or {}),
                    },
                )
                inserted += 1
            await session.commit()

    print(f"[ingest] done. inserted={inserted}, skipped_existing={skipped_existing}, skipped_empty={skipped_empty}")
    return {"inserted": inserted, "skipped_existing": skipped_existing, "skipped_empty": skipped_empty}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, help="CSV file with columns: module, persona, content, ...")
    parser.add_argument(
        "--seed-guidelines",
        action="store_true",
        help="Also seed from services/maxx_guidelines.py SKINMAX_PROTOCOLS.",
    )
    args = parser.parse_args()

    rows: List[Tuple[str, Optional[str], str, dict]] = []
    if args.csv:
        if not args.csv.exists():
            raise SystemExit(f"CSV not found: {args.csv}")
        rows.extend(_rows_from_csv(args.csv))
    if args.seed_guidelines:
        rows.extend(_rows_from_guidelines())
    if not rows:
        raise SystemExit("No rows to ingest. Pass --csv and/or --seed-guidelines.")

    await ingest(rows)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
