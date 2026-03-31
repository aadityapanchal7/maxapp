"""
OpenAI-backed LLM for Max chat (tools + vision) and triple face scans.
Use when settings.llm_provider == \"openai\".
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, Dict, List, Optional, Union

from config import settings
from models.scan import TripleFullScanResult, UmaxTripleScanResult
from services.prompt_loader import PromptKey, resolve_prompt
from services.sms_reply_style import sms_chat_appendix

from services.gemini_service import (
    MAX_CHAT_SYSTEM_PROMPT,
    TRIPLE_FULL_SYSTEM_PROMPT,
    UMAX_TRIPLE_SYSTEM_PROMPT,
    _mime_for_image_bytes,
    _normalize_triple_full_result,
    _normalize_umax_result,
    default_full_triple_dict,
    default_umax_triple_dict,
    _extend_umax_dict_with_full_defaults,
)

logger = logging.getLogger(__name__)


def _max_chat_tools_openai() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "modify_schedule",
                "description": "Modifies the user's active schedule from natural language. Only when they want calendar/task changes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "feedback": {"type": "string", "description": "Natural language description of the change."},
                    },
                    "required": ["feedback"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_maxx_schedule",
                "description": "Generate a personalised maxx schedule after onboarding fields are collected.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "maxx_id": {"type": "string", "description": "skinmax, heightmax, hairmax, fitmax, bonemax"},
                        "wake_time": {"type": "string"},
                        "sleep_time": {"type": "string"},
                        "outside_today": {"type": "boolean", "description": "Skinmax only; false for other modules"},
                        "skin_concern": {"type": "string"},
                        "age": {"type": "integer"},
                        "sex": {"type": "string"},
                        "gender": {"type": "string"},
                        "height": {"type": "string"},
                        "hair_type": {"type": "string"},
                        "scalp_state": {"type": "string"},
                        "daily_styling": {"type": "string"},
                        "thinning": {"type": "string"},
                        "hair_thinning": {"type": "string"},
                        "workout_frequency": {"type": "string"},
                        "tmj_history": {"type": "string"},
                        "mastic_gum_regular": {"type": "string"},
                        "heavy_screen_time": {"type": "string"},
                    },
                    "required": ["maxx_id", "wake_time", "sleep_time", "outside_today"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "stop_schedule",
                "description": "Deactivate a module schedule when the user wants to stop it.",
                "parameters": {
                    "type": "object",
                    "properties": {"maxx_id": {"type": "string"}},
                    "required": ["maxx_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_schedule_context",
                "description": "Store schedule habit context e.g. outside_today, wake_time.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["key", "value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "log_check_in",
                "description": "Log check-in data the user reported.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workout_done": {"type": "boolean"},
                        "missed": {"type": "boolean"},
                        "sleep_hours": {"type": "number"},
                        "calories": {"type": "integer"},
                        "mood": {"type": "string"},
                        "injury_area": {"type": "string"},
                        "injury_note": {"type": "string"},
                    },
                },
            },
        },
    ]


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
        self._model = (settings.openai_model or "gpt-4o-mini").strip()
        self._vision_model = (settings.openai_vision_model or self._model).strip()

    def _client(self):
        from openai import OpenAI

        key = (settings.openai_api_key or "").strip()
        if not key:
            raise ValueError("OPENAI_API_KEY is not set")
        return OpenAI(api_key=key)

    async def completion_text(self, prompt: str) -> str:
        def _sync() -> str:
            client = self._client()
            r = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
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
            client = self._client()
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

        for msg in chat_history[-15:]:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg.get("content") or ""})

        user_content: Union[str, List[dict]]
        if image_data:
            b64 = base64.standard_b64encode(image_data).decode("ascii")
            mime = _mime_for_image_bytes(image_data)
            user_content = [
                {"type": "text", "text": message if message else "Look at this image."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]
        else:
            user_content = message if message else ""

        messages.append({"role": "user", "content": user_content})

        tools = _max_chat_tools_openai()

        def _sync() -> dict:
            client = self._client()
            resp = client.chat.completions.create(
                model=self._vision_model if image_data else self._model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
            choice = resp.choices[0].message
            tool_calls_out: list[dict] = []
            for tc in choice.tool_calls or []:
                fn = tc.function
                raw_args = fn.arguments or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except json.JSONDecodeError:
                    args = {}
                tool_calls_out.append({"name": fn.name, "args": args})
            text = (choice.content or "").strip()
            return {
                "text": text or ("done. check your schedule." if tool_calls_out else ""),
                "tool_calls": tool_calls_out,
            }

        return await asyncio.to_thread(_sync)

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
