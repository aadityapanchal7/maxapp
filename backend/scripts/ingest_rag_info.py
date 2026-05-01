"""
Bulk-ingest every .pdf and .docx from rag_info/ into the Supabase rag_documents table.

Folder mapping:
    rag_info/bone_info/**    -> bonemax
    rag_info/fit_info/**     -> fitmax
    rag_info/general_info/** -> general   (cross-cutting knowledge, searched alongside any module)
    rag_info/hair_info/**    -> hairmax
    rag_info/height_info/**  -> heightmax
    rag_info/skin_info/**    -> skinmax

The script is fully idempotent: for each (maxx_id, doc_title) pair it deletes
existing rows before inserting fresh ones. Embeddings are generated when
OPENAI_API_KEY is configured; otherwise rows are inserted with NULL embedding.

Usage (from the backend/ directory):
    python scripts/ingest_rag_info.py              # full ingest
    python scripts/ingest_rag_info.py --dry-run    # preview without writing
    python scripts/ingest_rag_info.py --module skinmax   # only one module

Requirements:
    pip install pdfplumber python-docx
    .env with SUPABASE_DB_* credentials
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import re
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(_BACKEND_DIR / ".env")
load_dotenv(_BACKEND_DIR.parent / ".env", override=False)

RAG_INFO_DIR = _BACKEND_DIR.parent / "rag_info"

FOLDER_TO_MAXX: dict[str, str] = {
    "bone_info":    "bonemax",
    "fit_info":     "fitmax",
    "general_info": "general",
    "hair_info":    "hairmax",
    "height_info":  "heightmax",
    "skin_info":    "skinmax",
}

SUPPORTED_EXT = {".pdf", ".docx"}

CHUNK_MAX_CHARS = 1200


# ---------------------------------------------------------------------------
# File readers
# ---------------------------------------------------------------------------

def _read_pdf(path: pathlib.Path) -> str:
    import pdfplumber
    parts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text and text.strip():
                parts.append(text.strip())
    return "\n\n".join(parts)


def _read_docx(path: pathlib.Path) -> str:
    from docx import Document
    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(parts)


def read_file(path: pathlib.Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _read_pdf(path)
    if ext == ".docx":
        return _read_docx(path)
    raise ValueError(f"Unsupported extension: {ext}")


# ---------------------------------------------------------------------------
# Chunking -- paragraph-aware, keeps sections coherent
# ---------------------------------------------------------------------------

def _clean_title(filename: str) -> str:
    """Derive a human-readable doc_title from the filename."""
    name = pathlib.Path(filename).stem
    name = re.sub(r"^Module[_ ]+", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^draft--", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^\d+(\.\d+)?\s*", "", name)
    name = name.replace("_", " ").replace("  ", " ").strip()
    return name or filename


def chunk_text(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    """Split text into chunks at paragraph boundaries."""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        candidate = f"{buf}\n\n{para}".strip() if buf else para
        if len(candidate) > max_chars and buf:
            chunks.append(buf.strip())
            buf = para
        else:
            buf = candidate
    if buf.strip():
        chunks.append(buf.strip())
    return [c for c in chunks if c]


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_files(
    root: pathlib.Path,
    filter_module: str | None = None,
) -> list[tuple[str, str, pathlib.Path]]:
    """Walk rag_info/ and return (maxx_id, doc_title, path) triples."""
    jobs: list[tuple[str, str, pathlib.Path]] = []
    for folder_name, maxx_id in sorted(FOLDER_TO_MAXX.items()):
        if filter_module and maxx_id != filter_module:
            continue
        folder = root / folder_name
        if not folder.exists():
            print(f"[SKIP] folder not found: {folder}")
            continue
        for file_path in sorted(folder.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXT:
                continue
            doc_title = _clean_title(file_path.name)
            jobs.append((maxx_id, doc_title, file_path))
    return jobs


# ---------------------------------------------------------------------------
# DB upsert
# ---------------------------------------------------------------------------

async def upsert_document(
    session,
    maxx_id: str,
    doc_title: str,
    chunks: list[str],
    source_file: str,
) -> int:
    from sqlalchemy import text
    import json
    from datetime import datetime
    from services.rag_service import embed_batch

    await session.execute(
        text("DELETE FROM rag_documents WHERE maxx_id = :mid AND doc_title = :dt"),
        {"mid": maxx_id, "dt": doc_title},
    )

    embeddings: list[list[float]] = []
    can_embed = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    if can_embed and chunks:
        try:
            embeddings = await embed_batch(chunks)
        except Exception as e:
            print(f"[WARN] embedding generation failed for {maxx_id}/{doc_title}: {e}")
            embeddings = []

    now = datetime.utcnow().isoformat()
    for i, chunk in enumerate(chunks):
        emb_lit = None
        if i < len(embeddings) and embeddings[i]:
            emb = ",".join(f"{float(v):.8f}" for v in embeddings[i])
            emb_lit = f"[{emb}]"
        await session.execute(
            text(
                "INSERT INTO rag_documents (maxx_id, doc_title, chunk_index, content, metadata, embedding) "
                "VALUES (:maxx_id, :doc_title, :chunk_index, :content, CAST(:metadata AS jsonb), CAST(:embedding AS vector))"
            ),
            {
                "maxx_id": maxx_id,
                "doc_title": doc_title,
                "chunk_index": i,
                "content": chunk,
                "embedding": emb_lit,
                "metadata": json.dumps({
                    "source_file": os.path.basename(source_file),
                    "ingested_at": now,
                }),
            },
        )
    await session.commit()
    return len(chunks)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(
    dry_run: bool = False,
    filter_module: str | None = None,
) -> None:
    if not RAG_INFO_DIR.exists():
        print(f"[ERROR] rag_info/ not found at: {RAG_INFO_DIR}")
        sys.exit(1)

    jobs = discover_files(RAG_INFO_DIR, filter_module)
    if not jobs:
        print("[INFO] No documents found to ingest.")
        return

    print(f"Found {len(jobs)} document(s) to ingest:\n")
    for maxx_id, doc_title, path in jobs:
        print(f"  [{maxx_id:>10}]  {path.name}")
        print(f"  {'':>10}   -> \"{doc_title}\"")

    if dry_run:
        print("\n-- DRY RUN: reading files to show chunk counts --\n")
        total = 0
        for maxx_id, doc_title, path in jobs:
            try:
                text = read_file(path)
                chunks = chunk_text(text)
                chars = sum(len(c) for c in chunks)
                print(f"  [{maxx_id:>10}]  {doc_title}: {len(chunks)} chunks, {chars:,} chars")
                total += len(chunks)
            except Exception as e:
                print(f"  [{maxx_id:>10}]  {doc_title}: ERROR - {e}")
        print(f"\n  Total: {total} chunks (not written)")
        return

    from db.sqlalchemy import AsyncSessionLocal, init_db

    print("\nInitialising database ...")
    await init_db()

    total_chunks = 0
    errors: list[str] = []

    async with AsyncSessionLocal() as session:
        for maxx_id, doc_title, path in jobs:
            try:
                content = read_file(path)
                if not content.strip():
                    print(f"  [EMPTY]  {maxx_id}/{path.name}")
                    continue
                chunks = chunk_text(content)
                n = await upsert_document(session, maxx_id, doc_title, chunks, str(path))
                total_chunks += n
                print(f"  [OK]  {maxx_id}/{path.name}  ->  {n} chunks")
            except Exception as e:
                msg = f"  [ERROR]  {maxx_id}/{path.name}: {e}"
                print(msg)
                errors.append(msg)

    print(f"\nDone. {total_chunks} total chunks ingested across {len(jobs) - len(errors)} doc(s).")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for err in errors:
            print(err)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest rag_info/ PDFs and DOCX files into Supabase rag_documents"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Read and chunk files but don't write to DB",
    )
    parser.add_argument(
        "--module", default=None,
        help="Only ingest one module (e.g. skinmax, fitmax, bonemax, hairmax, general)",
    )
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, filter_module=args.module))


if __name__ == "__main__":
    main()
