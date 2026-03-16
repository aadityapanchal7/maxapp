"""
Guideline Service — Fetches maxx schedule guidelines from RDS with fallback to code.
Used by schedule_service for AI schedule generation.
"""

from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.rds_models import Maxx
from services.maxx_guidelines import MAXX_GUIDELINES, get_maxx_guideline as _get_fallback


def _maxx_row_to_guideline(m: Maxx) -> dict:
    """Convert RDS Maxx row to guideline dict format expected by schedule_service."""
    protocols = m.protocols or {}
    schedule_rules = m.schedule_rules or {}
    concern_mapping = m.concern_mapping or {}
    return {
        "label": m.label,
        "description": m.description or "",
        "schedule_rules": schedule_rules,
        "protocols": protocols,
        "concern_mapping": concern_mapping,
        "concern_question": m.concern_question,
        "concerns": m.concerns or [],
        "protocol_prompt_template": m.protocol_prompt_template,
        "recurring": True,
        "daily_tasks": True,
        "weekly_tasks": True,
    }


async def get_maxx_guideline_async(maxx_id: str, rds_db: Optional[AsyncSession] = None) -> Optional[dict]:
    """
    Fetch maxx guideline from RDS. Falls back to maxx_guidelines.py if RDS has no data.
    """
    if rds_db:
        result = await rds_db.execute(select(Maxx).where(Maxx.id == maxx_id))
        row = result.scalar_one_or_none()
        if row and (row.protocols or row.schedule_rules):
            return _maxx_row_to_guideline(row)
    return _get_fallback(maxx_id)


def resolve_concern(guideline: dict, skin_type: Optional[str] = None, explicit_concern: Optional[str] = None) -> str:
    """
    Resolve which concern to use. Explicit user choice overrides skin_type mapping.
    """
    protocols = guideline.get("protocols") or {}
    concern_mapping = guideline.get("concern_mapping") or {}
    if explicit_concern and explicit_concern in protocols:
        return explicit_concern
    fallback = list(protocols.keys())[0] if protocols else "aging"
    return concern_mapping.get(skin_type or "normal", fallback)


def build_protocol_prompt_section(guideline: dict, concern: str) -> str:
    """
    Build protocol text for the Gemini prompt using guideline's template and protocols.
    Works for any maxx (SkinMax, Hairmax, etc.) as long as protocols + template are defined.
    """
    protocols = guideline.get("protocols") or {}
    template = guideline.get("protocol_prompt_template")
    protocol = protocols.get(concern) or (list(protocols.values())[0] if protocols else {})

    if template and isinstance(protocol, dict):
        try:
            return template.format(**protocol)
        except KeyError:
            pass

    # Fallback: generic format if template missing or protocol has different keys
    if isinstance(protocol, dict):
        parts = [f"## PROTOCOL — {protocol.get('label', concern)}"]
        for k in ["am", "pm", "weekly", "sunscreen"]:
            if k in protocol and protocol[k]:
                parts.append(f"{k.upper()}: {protocol[k]}")
        return "\n".join(parts) + "\n"

    return ""
