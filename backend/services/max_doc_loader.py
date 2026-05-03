"""Parse max-doc files (data/maxes/<id>.md) into structured pieces.

Each doc has:
- YAML front-matter between leading '---' fences
- Markdown body (split by headings → RAG chunks)
- A trailing fenced ```yaml task_catalog block (extracted as task list)

Returned `MaxDoc` is consumed by ingest, schedule generation, and the
task-catalog cache.

This module has no I/O of its own beyond reading files — it's purely
a parser. Ingest scripts are responsible for persistence.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# Where max docs live, relative to the repo root.
DEFAULT_MAX_DOC_DIR = Path(__file__).resolve().parents[2] / "data" / "maxes"


@dataclass
class TaskDef:
    id: str
    title: str
    description: str
    duration_min: int
    default_window: str
    tags: list[str]
    applies_when: list[str]
    contraindicated_when: list[str]
    intensity: float
    evidence_section: Optional[str]
    cooldown_hours: int
    frequency: dict
    source_doc: str

    def to_db_row(self, maxx_id: str) -> dict:
        return {
            "id": self.id,
            "maxx_id": maxx_id,
            "title": self.title,
            "description": self.description,
            "duration_min": self.duration_min,
            "default_window": self.default_window,
            "tags": self.tags,
            "applies_when": self.applies_when,
            "contraindicated_when": self.contraindicated_when,
            "intensity": self.intensity,
            "evidence_section": self.evidence_section,
            "cooldown_hours": self.cooldown_hours,
            "frequency": self.frequency,
            "source_doc": self.source_doc,
        }


@dataclass
class RagChunk:
    """One section of the markdown body — one RAG row."""
    heading_path: list[str]   # e.g. ["Hyperpigmentation repair", "Phase 1 — Repair"]
    content: str
    chunk_index: int          # ordinal within doc

    @property
    def doc_title(self) -> str:
        return self.heading_path[0] if self.heading_path else "Overview"

    @property
    def section(self) -> str:
        return " > ".join(self.heading_path)


@dataclass
class MaxDoc:
    maxx_id: str
    display_name: str
    short_description: str
    schedule_design: dict
    required_fields: list[dict]
    optional_context: list[dict]
    prompt_modifiers: list[dict]
    chunks: list[RagChunk]
    tasks: list[TaskDef]
    source_path: str
    content_hash: str = ""

    def task_by_id(self, tid: str) -> Optional[TaskDef]:
        for t in self.tasks:
            if t.id == tid:
                return t
        return None


_FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_TASK_BLOCK_RE = re.compile(r"```yaml\s+task_catalog\s*\n(.*?)```", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def parse_max_doc(path: str | Path) -> MaxDoc:
    """Read and parse one max doc into a MaxDoc.

    Raises ValueError on malformed files (missing front-matter, missing
    maxx_id, unparseable task_catalog, etc) — fail loud rather than
    silently produce a half-broken doc.
    """
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    content_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    fm_match = _FRONT_MATTER_RE.match(raw)
    if not fm_match:
        raise ValueError(f"{path}: missing leading --- front-matter block")
    front_matter = yaml.safe_load(fm_match.group(1)) or {}
    body = raw[fm_match.end():]

    maxx_id = front_matter.get("maxx_id")
    if not maxx_id:
        raise ValueError(f"{path}: front-matter missing required 'maxx_id'")

    # Pull the task_catalog block out of the body before chunking.
    tasks: list[TaskDef] = []
    tm = _TASK_BLOCK_RE.search(body)
    if tm:
        task_yaml = tm.group(1)
        body = body[:tm.start()] + body[tm.end():]
        try:
            raw_tasks = yaml.safe_load(task_yaml) or []
        except yaml.YAMLError as e:
            raise ValueError(f"{path}: task_catalog YAML parse failed: {e}") from e
        if not isinstance(raw_tasks, list):
            raise ValueError(f"{path}: task_catalog must be a list, got {type(raw_tasks).__name__}")
        for raw_task in raw_tasks:
            tasks.append(_parse_task(raw_task, source_doc=str(path)))
    else:
        logger.info("max-doc %s has no task_catalog block (RAG-only)", path.name)

    chunks = _chunk_body(body)

    return MaxDoc(
        maxx_id=maxx_id,
        display_name=front_matter.get("display_name") or maxx_id,
        short_description=front_matter.get("short_description") or "",
        schedule_design=front_matter.get("schedule_design") or {},
        required_fields=front_matter.get("required_fields") or [],
        optional_context=front_matter.get("optional_context") or [],
        prompt_modifiers=front_matter.get("prompt_modifiers") or [],
        chunks=chunks,
        tasks=tasks,
        source_path=str(path),
        content_hash=content_hash,
    )


def parse_all_max_docs(directory: str | Path = DEFAULT_MAX_DOC_DIR) -> list[MaxDoc]:
    """Parse every *.md file under the directory."""
    directory = Path(directory)
    if not directory.exists():
        logger.warning("max-doc dir %s does not exist", directory)
        return []
    docs: list[MaxDoc] = []
    for path in sorted(directory.glob("*.md")):
        try:
            docs.append(parse_max_doc(path))
        except Exception as e:
            logger.error("Failed to parse %s: %s", path, e)
    return docs


def _parse_task(raw: dict, *, source_doc: str) -> TaskDef:
    """Validate + coerce a raw task dict into a TaskDef."""
    if not isinstance(raw, dict):
        raise ValueError(f"task entry must be mapping, got {type(raw).__name__}: {raw}")
    missing = [k for k in ("id", "title", "description") if not raw.get(k)]
    if missing:
        raise ValueError(f"task missing required keys {missing}: {raw}")

    tags = raw.get("tags") or []
    if not isinstance(tags, list):
        tags = [tags]

    aw = raw.get("applies_when") or []
    if isinstance(aw, str):
        aw = [aw]
    cw = raw.get("contraindicated_when") or []
    if isinstance(cw, str):
        cw = [cw]

    freq = raw.get("frequency") or {"type": "daily", "n": 1}
    if not isinstance(freq, dict) or "type" not in freq:
        raise ValueError(f"task {raw['id']}: frequency must be {{type:..., n:...}}")

    return TaskDef(
        id=str(raw["id"]),
        title=str(raw["title"]).strip(),
        description=str(raw["description"]).strip(),
        duration_min=int(raw.get("duration_min", 5)),
        default_window=str(raw.get("default_window", "flexible")),
        tags=[str(t) for t in tags],
        applies_when=[str(e) for e in aw],
        contraindicated_when=[str(e) for e in cw],
        intensity=float(raw.get("intensity", 0.3)),
        evidence_section=raw.get("evidence_section"),
        cooldown_hours=int(raw.get("cooldown_hours", 0)),
        frequency=freq,
        source_doc=source_doc,
    )


def _chunk_body(body: str) -> list[RagChunk]:
    """Split markdown by heading hierarchy — one chunk per leaf section.

    The chunker preserves the heading path so retrieval can cite the section.
    Leading content before any heading is dropped (front-matter is the
    canonical metadata; intro paragraphs without a heading are rare).
    """
    lines = body.splitlines()
    chunks: list[RagChunk] = []
    heading_path: list[str] = []
    buf: list[str] = []
    chunk_idx = 0

    def flush():
        nonlocal chunk_idx, buf
        text = "\n".join(buf).strip()
        if text and heading_path:
            chunks.append(RagChunk(
                heading_path=list(heading_path),
                content=text,
                chunk_index=chunk_idx,
            ))
            chunk_idx += 1
        buf = []

    for line in lines:
        m = _HEADING_RE.match(line.strip())
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            heading_path[:] = heading_path[: level - 1]
            heading_path.append(title)
            continue
        buf.append(line)
    flush()

    return chunks
