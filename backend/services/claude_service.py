"""
Claude Service - Face scan vision analysis via Anthropic API.
Uses claude-opus-4-8 (or whatever anthropic_model is set to) with adaptive thinking.
"""

import base64
import json
import logging
from typing import Any, Dict

import anthropic

from config import settings
from models.scan import TripleFullScanResult
from services.gemini_service import (
    TRIPLE_FULL_SYSTEM_PROMPT,
    _mime_for_image_bytes,
    _normalize_triple_full_result,
    _extend_umax_dict_with_full_defaults,
    default_full_triple_dict,
)
from services.prompt_loader import PromptKey, resolve_prompt

logger = logging.getLogger(__name__)


def _b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("utf-8")


def _media_type(data: bytes) -> str:
    mime = _mime_for_image_bytes(data)
    # Anthropic accepts image/jpeg, image/png, image/gif, image/webp
    if mime in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        return mime
    return "image/jpeg"


class ClaudeService:
    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def analyze_triple_full(
        self,
        front: bytes,
        left: bytes,
        right: bytes,
        onboarding_json: str = "{}",
    ) -> Dict[str, Any]:
        if not front or not left or not right:
            return default_full_triple_dict("Missing one or more photos.")
        if not settings.anthropic_api_key or not str(settings.anthropic_api_key).strip():
            return default_full_triple_dict("Set ANTHROPIC_API_KEY on the API server for AI ratings.")

        client = self._get_client()
        model = (settings.anthropic_model or "claude-opus-4-8").strip()
        ctx = (onboarding_json or "{}").strip()[:12000]

        system_prompt = resolve_prompt(PromptKey.TRIPLE_FULL_SYSTEM, TRIPLE_FULL_SYSTEM_PROMPT)

        user_content = [
            {
                "type": "text",
                "text": ctx + "\n\nPHOTOS — analyze all three:\n\nFRONT:",
            },
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _media_type(front),
                    "data": _b64(front),
                },
            },
            {"type": "text", "text": "\nLEFT PROFILE:"},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _media_type(left),
                    "data": _b64(left),
                },
            },
            {"type": "text", "text": "\nRIGHT PROFILE:"},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _media_type(right),
                    "data": _b64(right),
                },
            },
            {
                "type": "text",
                "text": (
                    "\n\nReturn ONLY valid JSON matching the TripleFullScanResult schema "
                    "(psl_score, psl_tier, potential, archetype, appeal, ascension_time_months, age_score, "
                    "weakest_link, aura_tags, feature_scores, proportions, side_profile, masculinity_index, "
                    "mog_percentile, glow_up_potential, "
                    # Viral coach metrics — required, same as the system instructions.
                    "halo_feature, bottleneck, bottleneck_max, sex_appeal, trust_appeal, appeal_quadrant, "
                    "dimorphism, dimorphism_note, glow_up_label, first_move, "
                    "metrics, preview_blurb, problems, suggested_modules). "
                    "No markdown fences, no commentary."
                ),
            },
        ]

        try:
            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = _extract_text(response)
            raw = _strip_fences(raw)
            parsed = TripleFullScanResult.model_validate_json(raw)
            result = _normalize_triple_full_result(parsed)
            result["source"] = "claude_triple_full"
            return result
        except Exception as e:
            logger.warning("[Claude] analyze_triple_full failed (%s: %s); trying plain JSON fallback", type(e).__name__, e)
            try:
                response2 = await client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_content}],
                )
                raw2 = _strip_fences(_extract_text(response2))
                parsed2 = TripleFullScanResult.model_validate_json(raw2)
                result2 = _normalize_triple_full_result(parsed2)
                result2["source"] = "claude_triple_full"
                return result2
            except Exception as e2:
                logger.exception("[Claude] analyze_triple_full fallback also failed: %s", e2)
                return _extend_umax_dict_with_full_defaults(
                    default_full_triple_dict(str(e2)[:200]), str(e2)[:200]
                )


    async def simple_completion(
        self,
        user_prompt: str,
        system_prompt: str = "",
        max_tokens: int = 1200,
        timeout: float = 45.0,
    ) -> str:
        """Single-turn text completion — no history, no coaching context.

        Never raises: a hung/erroring/timed-out Anthropic call returns "" so
        existing callers (which already treat "" as "unavailable" and degrade)
        keep working unchanged.
        """
        from config import settings as _settings
        if not (_settings.anthropic_api_key or "").strip():
            return ""
        client = self._get_client()
        model = (_settings.anthropic_model or "claude-haiku-4-5").strip()
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user_prompt}],
            "timeout": timeout,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        try:
            response = await client.messages.create(**kwargs)
        except anthropic.APIError as e:
            logger.warning("[Claude] simple_completion failed (%s: %s)", type(e).__name__, e)
            return ""
        except Exception as e:
            logger.warning("[Claude] simple_completion unexpected error (%s: %s)", type(e).__name__, e)
            return ""
        return _extract_text(response)


def _extract_text(response: anthropic.types.Message) -> str:
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


def _strip_fences(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        parts = s.split("```", 2)
        if len(parts) >= 2:
            body = parts[1]
            if body.lstrip().startswith("json"):
                body = body.lstrip()[4:]
            s = body.strip()
    return s


claude_service = ClaudeService()
