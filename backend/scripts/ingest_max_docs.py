"""Ingest data/maxes/*.md into Supabase.

For each max doc:
  1. Parse via max_doc_loader.
  2. Skip if `max_doc_meta.content_hash` already matches (no-op).
  3. Otherwise:
     - Replace `max_doc_meta` row.
     - Replace `task_catalog` rows for this maxx_id.
     - Replace `rag_documents` rows for this maxx_id (chunks + embeddings).

Run from repo root:
    python -m backend.scripts.ingest_max_docs                # ingest all
    python -m backend.scripts.ingest_max_docs --max skinmax  # one max
    python -m backend.scripts.ingest_max_docs --force        # ignore content_hash

Idempotent and safe to re-run. After ingest, hit the `/admin/rag/reload`
endpoint (or call task_catalog_service.reload_catalog()) to refresh
in-memory caches.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from uuid import uuid4

# Allow `python backend/scripts/ingest_max_docs.py` and `python -m ...`.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text   # noqa: E402

from db.sqlalchemy import AsyncSessionLocal   # noqa: E402
from services.max_doc_loader import MaxDoc, parse_all_max_docs, parse_max_doc, DEFAULT_MAX_DOC_DIR   # noqa: E402
from services.rag_service import embed_batch, _vec_to_pg_str   # noqa: E402

logger = logging.getLogger("ingest_max_docs")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def _existing_hash(session, maxx_id: str) -> str | None:
    res = await session.execute(
        text("SELECT content_hash FROM max_doc_meta WHERE maxx_id = :mid"),
        {"mid": maxx_id},
    )
    row = res.first()
    return row[0] if row else None


async def _upsert_meta(session, doc: MaxDoc) -> None:
    await session.execute(
        text(
            """
            INSERT INTO max_doc_meta (
                maxx_id, display_name, short_description,
                schedule_design, required_fields, optional_context, prompt_modifiers,
                source_doc, content_hash, updated_at
            ) VALUES (
                :mid, :name, :desc,
                CAST(:sd AS jsonb), CAST(:rf AS jsonb), CAST(:oc AS jsonb), CAST(:pm AS jsonb),
                :src, :hash, NOW()
            )
            ON CONFLICT (maxx_id) DO UPDATE SET
                display_name      = EXCLUDED.display_name,
                short_description = EXCLUDED.short_description,
                schedule_design   = EXCLUDED.schedule_design,
                required_fields   = EXCLUDED.required_fields,
                optional_context  = EXCLUDED.optional_context,
                prompt_modifiers  = EXCLUDED.prompt_modifiers,
                source_doc        = EXCLUDED.source_doc,
                content_hash      = EXCLUDED.content_hash,
                updated_at        = NOW()
            """
        ),
        {
            "mid": doc.maxx_id,
            "name": doc.display_name,
            "desc": doc.short_description,
            "sd": json.dumps(doc.schedule_design),
            "rf": json.dumps(doc.required_fields),
            "oc": json.dumps(doc.optional_context),
            "pm": json.dumps(doc.prompt_modifiers),
            "src": doc.source_path,
            "hash": doc.content_hash,
        },
    )


async def _upsert_tasks(session, doc: MaxDoc) -> int:
    # Delete + insert is simpler than per-row UPSERT and the catalog is small.
    await session.execute(
        text("DELETE FROM task_catalog WHERE maxx_id = :mid"),
        {"mid": doc.maxx_id},
    )
    for task in doc.tasks:
        row = task.to_db_row(doc.maxx_id)
        await session.execute(
            text(
                """
                INSERT INTO task_catalog (
                    id, maxx_id, title, description, duration_min, default_window,
                    tags, applies_when, contraindicated_when, intensity,
                    evidence_section, cooldown_hours, frequency, source_doc, updated_at
                ) VALUES (
                    :id, :mid, :title, :desc, :dur, :win,
                    CAST(:tags AS jsonb), CAST(:aw AS jsonb), CAST(:cw AS jsonb), :inten,
                    :ev, :cd, CAST(:freq AS jsonb), :src, NOW()
                )
                """
            ),
            {
                "id": row["id"],
                "mid": row["maxx_id"],
                "title": row["title"],
                "desc": row["description"],
                "dur": row["duration_min"],
                "win": row["default_window"],
                "tags": json.dumps(row["tags"]),
                "aw": json.dumps(row["applies_when"]),
                "cw": json.dumps(row["contraindicated_when"]),
                "inten": row["intensity"],
                "ev": row["evidence_section"],
                "cd": row["cooldown_hours"],
                "freq": json.dumps(row["frequency"]),
                "src": row["source_doc"],
            },
        )
    return len(doc.tasks)


async def _upsert_chunks(session, doc: MaxDoc) -> int:
    """Replace rag_documents rows for this maxx_id with chunks from doc.

    Embeddings are generated in one batch — one network round-trip per max
    rather than per-chunk.
    """
    await session.execute(
        text("DELETE FROM rag_documents WHERE maxx_id = :mid"),
        {"mid": doc.maxx_id},
    )
    if not doc.chunks:
        return 0

    # Compose the texts that will be embedded — heading path included so
    # vector search retrieves with section context.
    texts = [
        f"{c.section}\n\n{c.content}" if c.section else c.content
        for c in doc.chunks
    ]
    try:
        embeddings = await embed_batch(texts)
    except Exception as e:
        logger.warning("embedding failed for %s, ingesting without vectors: %s", doc.maxx_id, e)
        embeddings = []

    for i, chunk in enumerate(doc.chunks):
        emb = embeddings[i] if i < len(embeddings) else None
        emb_lit = _vec_to_pg_str(emb) if emb else None
        params = {
            "maxx_id": doc.maxx_id,
            "doc_title": chunk.doc_title,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "metadata": json.dumps({
                "section": chunk.section,
                "heading_path": chunk.heading_path,
                "source": doc.source_path,
            }),
            "embedding": emb_lit,
        }
        if emb_lit:
            sql = text(
                """
                INSERT INTO rag_documents (maxx_id, doc_title, chunk_index, content, metadata, embedding)
                VALUES (:maxx_id, :doc_title, :chunk_index, :content, CAST(:metadata AS jsonb), CAST(:embedding AS vector))
                """
            )
        else:
            sql = text(
                """
                INSERT INTO rag_documents (maxx_id, doc_title, chunk_index, content, metadata)
                VALUES (:maxx_id, :doc_title, :chunk_index, :content, CAST(:metadata AS jsonb))
                """
            )
            params.pop("embedding")
        await session.execute(sql, params)
    return len(doc.chunks)


async def _ingest_one(doc: MaxDoc, *, force: bool) -> dict:
    t0 = time.perf_counter()
    async with AsyncSessionLocal() as session:
        prior_hash = await _existing_hash(session, doc.maxx_id)
        if not force and prior_hash == doc.content_hash:
            return {"maxx": doc.maxx_id, "status": "skipped (unchanged)", "ms": 0}
        # The SELECT above auto-started a transaction on this session. Commit
        # it before opening a fresh `session.begin()` for the upsert work.
        await session.commit()

        async with session.begin():
            await _upsert_meta(session, doc)
            n_tasks = await _upsert_tasks(session, doc)
            n_chunks = await _upsert_chunks(session, doc)

    elapsed = (time.perf_counter() - t0) * 1000
    return {
        "maxx": doc.maxx_id,
        "status": "ingested",
        "tasks": n_tasks,
        "chunks": n_chunks,
        "ms": int(elapsed),
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", default=None, help="Ingest only this maxx_id")
    parser.add_argument("--force", action="store_true", help="Ignore content_hash")
    parser.add_argument("--dir", default=str(DEFAULT_MAX_DOC_DIR), help="Doc directory")
    parser.add_argument("--dry-run", action="store_true", help="Parse only — no DB writes")
    args = parser.parse_args()

    docs = parse_all_max_docs(args.dir)
    if args.max:
        docs = [d for d in docs if d.maxx_id == args.max]
        if not docs:
            print(f"no doc found for maxx_id={args.max}")
            return 1

    print(f"Found {len(docs)} max-doc(s):")
    for d in docs:
        print(f"  - {d.maxx_id:>12}  {len(d.chunks):>3} chunks  {len(d.tasks):>3} tasks  ({Path(d.source_path).name})")

    if args.dry_run:
        print("\n--dry-run: no DB writes")
        return 0

    print("\nIngesting...")
    results = []
    for doc in docs:
        try:
            r = await _ingest_one(doc, force=args.force)
        except Exception as e:
            logger.exception("ingest failed: %s", e)
            r = {"maxx": doc.maxx_id, "status": f"FAILED: {e}", "ms": 0}
        results.append(r)
        print(f"  [{r['status']:>22}]  {r['maxx']:>12}  ({r.get('ms', 0)}ms)")

    print("\nDone. Call task_catalog_service.reload_catalog() to refresh in-memory caches.")
    failed = [r for r in results if r["status"].startswith("FAILED")]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
