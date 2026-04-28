"""
LLM service for Max:
  * `chat()` calls the Hugging Face Dedicated Inference Endpoint (model="tgi")
    via the OpenAI SDK compatibility layer (HF_TOKEN, base_url=/v1).
  * Vision methods (`analyze_triple_*`, `completion_vision`) keep using OpenAI
    directly with OPENAI_API_KEY because the HF TGI text endpoint can't
    accept image input.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional

from config import settings
from models.scan import TripleFullScanResult, UmaxTripleScanResult
from services.prompt_constants import MAX_CHAT_SYSTEM_PROMPT, TRIPLE_FULL_SYSTEM_PROMPT, UMAX_TRIPLE_SYSTEM_PROMPT
from services.prompt_loader import PromptKey, resolve_prompt
from services.sms_reply_style import sms_chat_appendix

from services.gemini_service import (
    _mime_for_image_bytes,
    _normalize_triple_full_result,
    _normalize_umax_result,
    default_full_triple_dict,
    default_umax_triple_dict,
    _extend_umax_dict_with_full_defaults,
)

logger = logging.getLogger(__name__)


def _strip_json_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        parts = t.split("```", 2)
        if len(parts) >= 2:
            t = parts[1]
            if t.lstrip().startswith("json"):
                t = t.lstrip()[4:].lstrip()
    return t.strip()


class OpenAIService:
    def __init__(self) -> None:
        # Vision still goes through real OpenAI -- HF TGI text endpoints
        # don't accept image input.
        self._vision_model = (settings.openai_vision_model or settings.openai_model or "gpt-4o").strip()
        # Chat goes through the HF Dedicated Inference Endpoint via OpenAI compat.
        self._chat_model = (settings.hf_model or "tgi").strip()

    def _chat_client(self):
        """OpenAI SDK pointed at the Hugging Face dedicated endpoint /v1."""
        from openai import OpenAI

        key = (settings.hf_token or "").strip()
        if not key:
            raise ValueError("HF_TOKEN is not set")
        base_url = (settings.hf_endpoint_url or "").strip()
        if not base_url:
            raise ValueError("HF_ENDPOINT_URL is not set")
        return OpenAI(api_key=key, base_url=base_url)

    def _vision_client(self):
        """Real OpenAI client for face-scan vision calls."""
        from openai import OpenAI

        key = (settings.openai_api_key or "").strip()
        if not key:
            raise ValueError("OPENAI_API_KEY is not set")
        return OpenAI(api_key=key)

    async def completion_text(self, prompt: str) -> str:
        def _sync() -> str:
            client = self._chat_client()
            r = client.chat.completions.create(
                model=self._chat_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7,
            )
            return (r.choices[0].message.content or "").strip()

        return await asyncio.to_thread(_sync)

    async def completion_vision(self, prompt: str, images: List[bytes], json_mode: bool = False) -> str:
        def _b64_url(b: bytes) -> str:
            m = _mime_for_image_bytes(b)
            return f"data:{m};base64,{base64.standard_b64encode(b).decode('ascii')}"

        user_content: List[dict] = [{"type": "text", "text": prompt}]
        for img in images:
            user_content.append({"type": "image_url", "image_url": {"url": _b64_url(img)}})

        def _sync() -> str:
            client = self._vision_client()
            kwargs: dict = {
                "model": self._vision_model,
                "messages": [{"role": "user", "content": user_content}],
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            r = client.chat.completions.create(**kwargs)
            return (r.choices[0].message.content or "").strip()

        return await asyncio.to_thread(_sync)

    async def chat(
        self,
        message: str,
        chat_history: List[dict],
        user_context: Optional[dict] = None,
        image_data: Optional[bytes] = None,
        delivery_channel: str = "app",
    ) -> dict:
        # NOTE: image_data is accepted for backward compatibility but ignored
        # on this path -- the HF dedicated endpoint is text-only. Image-bearing
        # turns should go through the vision pipeline (face-scan endpoints).
        context_str = user_context.get("coaching_context", "") if user_context else ""
        if not context_str and user_context:
            if user_context.get("latest_scan"):
                scan = user_context["latest_scan"]
                context_str += f"\nLATEST SCAN: score={scan.get('overall_score', '?')}/10"
                if scan.get("focus_areas"):
                    context_str += f", focus={scan['focus_areas']}"
            if user_context.get("onboarding"):
                ob = user_context["onboarding"]
                bits = [
                    f"{k}: {', '.join(v) if isinstance(v, list) else v}"
                    for k, v in ob.items()
                    if v and k in ("skin_type", "goals", "gender", "age")
                ]
                if bits:
                    context_str += f"\nPROFILE: {' | '.join(bits)}"
            if user_context.get("active_schedule"):
                schedule = user_context["active_schedule"]
                label = schedule.get("course_title") or schedule.get("maxx_id") or "?"
                context_str += f"\nSCHEDULE: {label}"
            if user_context.get("active_maxx_schedule"):
                ms = user_context["active_maxx_schedule"]
                context_str += f"\nActive {ms.get('maxx_id')} schedule exists."

        chat_prompt = await asyncio.to_thread(
            resolve_prompt, PromptKey.MAX_CHAT_SYSTEM, MAX_CHAT_SYSTEM_PROMPT
        )
        if context_str:
            chat_prompt += f"\n\n## USER CONTEXT:\n{context_str}"
        _sms_extra = sms_chat_appendix(delivery_channel)
        if _sms_extra:
            chat_prompt += "\n\n" + _sms_extra

        messages: list[dict] = [{"role": "system", "content": chat_prompt}]

        for msg in chat_history[-10:]:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg.get("content") or ""})

        messages.append({"role": "user", "content": message if message else ""})

        def _sync() -> dict:
            client = self._chat_client()
            resp = client.chat.completions.create(
                model=self._chat_model,
                messages=messages,
                max_tokens=500,
                temperature=0.7,
                timeout=20,
            )
            text = (resp.choices[0].message.content or "").strip()
            return {"text": text, "tool_calls": []}

        return await asyncio.wait_for(asyncio.to_thread(_sync), timeout=22.0)

    async def analyze_triple_umax(self, front: bytes, left: bytes, right: bytes) -> Dict[str, Any]:
        if not front or not left or not right:
            return default_umax_triple_dict("Missing one or more photos.")
        if not (settings.openai_api_key or "").strip():
            return default_umax_triple_dict("Set OPENAI_API_KEY on the API server for AI ratings.")

        triple_intro = await asyncio.to_thread(
            resolve_prompt, PromptKey.UMAX_TRIPLE_SYSTEM, UMAX_TRIPLE_SYSTEM_PROMPT
        )
        user_text = triple_intro + "\n\nRespond with JSON only matching: overall_score (number), metrics (array of {id,label,score,summary}), preview_blurb (string)."

        try:
            raw = await self.completion_vision(user_text, [front, left, right], json_mode=True)
            parsed = UmaxTripleScanResult.model_validate_json(_strip_json_fences(raw))
            return _normalize_umax_result(parsed)
        except Exception as e:
            logger.warning("[OpenAI] analyze_triple_umax failed: %s", e)
            return default_umax_triple_dict(f"Could not complete AI rating. ({str(e)[:120]})")

    async def analyze_triple_full(
        self,
        front: bytes,
        left: bytes,
        right: bytes,
        onboarding_json: str = "{}",
    ) -> Dict[str, Any]:
        if not front or not left or not right:
            return default_full_triple_dict("Missing one or more photos.")
        if not (settings.openai_api_key or "").strip():
            return default_full_triple_dict("Set OPENAI_API_KEY on the API server for AI ratings.")

        ctx = (onboarding_json or "{}").strip()[:12000]
        full_intro = await asyncio.to_thread(
            resolve_prompt, PromptKey.TRIPLE_FULL_SYSTEM, TRIPLE_FULL_SYSTEM_PROMPT
        )
        user_text = full_intro + "\n\nUSER ONBOARDING JSON:\n" + ctx + "\n\nRespond with JSON only matching the full scan schema from your instructions."

        try:
            raw = await self.completion_vision(user_text, [front, left, right], json_mode=True)
            parsed = TripleFullScanResult.model_validate_json(_strip_json_fences(raw))
            return _normalize_triple_full_result(parsed)
        except Exception as e:
            logger.warning("[OpenAI] analyze_triple_full failed: %s", e)
            try:
                base = await self.analyze_triple_umax(front, left, right)
                return _extend_umax_dict_with_full_defaults(base, str(e)[:200])
            except Exception as e2:
                return default_full_triple_dict(str(e2)[:200])


openai_service = OpenAIService()
