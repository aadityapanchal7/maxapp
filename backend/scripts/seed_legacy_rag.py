"""One-time script to seed the 6 legacy backend/rag_content/ files into rag_documents.

Usage (from backend/ directory):
    python scripts/seed_legacy_rag.py

Idempotent: skips any (maxx_id, doc_title) pair that already exists in the table.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(_BACKEND_DIR / ".env")


VALID_MAXX_IDS = {"skinmax", "fitmax", "hairmax", "heightmax", "bonemax"}


async def main() -> None:
    from db.sqlalchemy import AsyncSessionLocal
    from sqlalchemy import text

    legacy_dir = _BACKEND_DIR / "rag_content"
    if not legacy_dir.exists():
        print(f"[SKIP] {legacy_dir} does not exist")
        return

    docs: list[dict] = []
    for maxx_dir in sorted(legacy_dir.iterdir()):
        if not maxx_dir.is_dir() or maxx_dir.name not in VALID_MAXX_IDS:
            continue
        for md in sorted(maxx_dir.glob("*.md")):
            content = md.read_text(encoding="utf-8")
            if not content.strip():
                continue
            doc_title = md.stem.replace("-", " ").replace("_", " ").title()
            docs.append({
                "maxx_id": maxx_dir.name,
                "doc_title": doc_title,
                "content": content,
            })

    if not docs:
        print("[SKIP] No legacy .md files found")
        return

    async with AsyncSessionLocal() as session:
        inserted = 0
        skipped = 0
        for doc in docs:
            exists = await session.execute(
                text(
                    "SELECT 1 FROM rag_documents "
                    "WHERE maxx_id = :mid AND doc_title = :dt LIMIT 1"
                ),
                {"mid": doc["maxx_id"], "dt": doc["doc_title"]},
            )
            if exists.fetchone():
                print(f"  [exists] {doc['maxx_id']}/{doc['doc_title']}")
                skipped += 1
                continue

            await session.execute(
                text(
                    "INSERT INTO rag_documents (maxx_id, doc_title, chunk_index, content) "
                    "VALUES (:maxx_id, :doc_title, 0, :content)"
                ),
                doc,
            )
            print(f"  [insert] {doc['maxx_id']}/{doc['doc_title']}")
            inserted += 1

        await session.commit()

    print(f"\nDone: {inserted} inserted, {skipped} skipped (already existed)")


if __name__ == "__main__":
    asyncio.run(main())
