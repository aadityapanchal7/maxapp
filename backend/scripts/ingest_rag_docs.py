"""Validate and refresh the live file-based RAG docs.

This script no longer writes vectors to Postgres. It reads ``rag_docs/``,
verifies that each file produces chunks under the live markdown chunker, and
clears the in-process index cache so the next request re-loads fresh content.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from services.rag_ingest import ingest_doc
from services.rag_service import reload_indexes

RAG_DOCS_DIR = _BACKEND_DIR.parent / "rag_docs"
SUPPORTED_EXTENSIONS = {".md", ".txt", ".docx"}
VALID_MAXX_IDS = {"skinmax", "fitmax", "hairmax", "heightmax", "bonemax"}


def read_file_content(path: pathlib.Path) -> str:
    ext = path.suffix.lower()
    if ext == ".docx":
        from docx import Document

        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    return path.read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate rag_docs/ for the live file-based RAG")
    parser.add_argument("--maxx_id", default=None, help="Only validate one module")
    parser.add_argument("--dry-run", action="store_true", help="Do not clear the in-memory indexes")
    args = parser.parse_args()

    if not RAG_DOCS_DIR.exists():
        raise SystemExit(f"rag_docs/ not found at {RAG_DOCS_DIR}")

    jobs: list[tuple[str, pathlib.Path]] = []
    for maxx_dir in sorted(RAG_DOCS_DIR.iterdir()):
        if not maxx_dir.is_dir():
            continue
        maxx_id = maxx_dir.name.lower()
        if maxx_id not in VALID_MAXX_IDS:
            continue
        if args.maxx_id and maxx_id != args.maxx_id:
            continue
        for doc_file in sorted(maxx_dir.iterdir()):
            if doc_file.suffix.lower() in SUPPORTED_EXTENSIONS:
                jobs.append((maxx_id, doc_file))

    if not jobs:
        print("[INFO] No documents found to validate.")
        return

    total_chunks = 0
    for maxx_id, doc_file in jobs:
        content = read_file_content(doc_file)
        doc_title = doc_file.stem.replace("-", " ").replace("_", " ").title()
        n = ingest_doc(
            content=content,
            maxx_id=maxx_id,
            doc_title=doc_title,
            source_file=str(doc_file),
        )
        total_chunks += n
        print(f"[OK] {maxx_id}/{doc_file.name} -> {n} chunks")

    if args.dry_run:
        print(f"\nValidated {len(jobs)} docs ({total_chunks} chunks). Index cache left untouched.")
        return

    reload_indexes()
    print(f"\nValidated {len(jobs)} docs ({total_chunks} chunks). Cleared in-memory RAG indexes.")


if __name__ == "__main__":
    main()
