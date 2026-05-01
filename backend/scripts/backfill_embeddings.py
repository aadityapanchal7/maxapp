"""Backfill rag_documents.embedding for rows where it is NULL.

Usage:
    python scripts/backfill_embeddings.py
    python scripts/backfill_embeddings.py --module skinmax
    python scripts/backfill_embeddings.py --batch-size 64
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(_BACKEND_DIR / ".env")
load_dotenv(_BACKEND_DIR.parent / ".env", override=False)


async def run(module: str | None, batch_size: int) -> None:
    from sqlalchemy import text

    from db.sqlalchemy import AsyncSessionLocal, init_db
    from services.rag_service import embed_batch

    await init_db()
    total = 0
    updated = 0

    where = "WHERE embedding IS NULL"
    params: dict[str, object] = {}
    if module:
        where += " AND maxx_id = :module"
        params["module"] = module

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                f"""
                SELECT id::text AS id, content
                FROM rag_documents
                {where}
                ORDER BY maxx_id, doc_title, chunk_index
                """
            ),
            params,
        )
        rows = result.fetchall()
        total = len(rows)
        if not rows:
            print("No rows need backfill.")
            return

        print(f"Backfilling embeddings for {total} row(s)...")
        for i in range(0, total, batch_size):
            batch = rows[i : i + batch_size]
            texts = [str(r.content or "").strip() for r in batch]
            embeddings = await embed_batch(texts, batch_size=batch_size)
            for row, emb in zip(batch, embeddings):
                emb_lit = "[" + ",".join(f"{float(v):.8f}" for v in emb) + "]"
                await session.execute(
                    text(
                        """
                        UPDATE rag_documents
                        SET embedding = CAST(:embedding AS vector)
                        WHERE id::text = :id
                        """
                    ),
                    {"id": row.id, "embedding": emb_lit},
                )
            await session.commit()
            updated += len(batch)
            print(f"  updated {updated}/{total}")

    print(f"Done. Backfilled {updated} row(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill rag_documents embeddings")
    parser.add_argument("--module", default=None, help="Optional maxx_id filter")
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding batch size")
    args = parser.parse_args()
    asyncio.run(run(module=args.module, batch_size=max(1, args.batch_size)))


if __name__ == "__main__":
    main()
