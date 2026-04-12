"""
LangChain StructuredTool definitions — SCHEMA / REFERENCE ONLY for the 9 Max chat tools.

WARNING: Do NOT import ``CHAT_TOOLS`` expecting runnable tools. The stub ``_stub``
implementations return empty strings and are not wired to the chat pipeline.

The REAL tool implementations (async, DB-bound) live in
``services.lc_agent.make_chat_tools()`` and are passed to ``run_chat_agent()``.

These ``StructuredTool`` entries replace duplicate JSON schemas that were
previously maintained in openai_service.py and gemini_service.py. They may be
used for documentation, schema export, or future LLM binding — not execution.
"""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Input schemas (Pydantic models used by StructuredTool for schema generation)
# ---------------------------------------------------------------------------

class ModifyScheduleInput(BaseModel):
    feedback: str = Field(description="Natural language description of the change.")


class GenerateMaxxScheduleInput(BaseModel):
    maxx_id: str = Field(description="skinmax, heightmax, hairmax, fitmax, bonemax")
    wake_time: str = Field(description="Wake time, e.g. '07:00'")
    sleep_time: str = Field(description="Sleep time, e.g. '23:00'")
    outside_today: bool = Field(description="Skinmax only; false for other modules")
    skin_concern: Optional[str] = Field(default=None)
    age: Optional[int] = Field(default=None)
    sex: Optional[str] = Field(default=None)
    gender: Optional[str] = Field(default=None)
    height: Optional[str] = Field(default=None)
    hair_type: Optional[str] = Field(default=None)
    scalp_state: Optional[str] = Field(default=None)
    daily_styling: Optional[str] = Field(default=None)
    thinning: Optional[str] = Field(default=None)
    hair_thinning: Optional[str] = Field(default=None)
    workout_frequency: Optional[str] = Field(default=None)
    tmj_history: Optional[str] = Field(default=None)
    mastic_gum_regular: Optional[str] = Field(default=None)
    heavy_screen_time: Optional[str] = Field(default=None)
    body_weight_kg: Optional[float] = Field(
        default=None, description="FitMax: body weight in kg"
    )
    training_days_per_week: Optional[int] = Field(
        default=None, description="FitMax: training days per week (typically 3-6)"
    )
    training_experience: Optional[str] = Field(
        default=None, description="FitMax: beginner, intermediate, or advanced"
    )
    fitmax_equipment: Optional[str] = Field(default=None, description="FitMax: equipment available")
    session_minutes: Optional[int] = Field(default=None, description="FitMax: typical session length in minutes")
    daily_activity_level: Optional[str] = Field(
        default=None,
        description="FitMax: sedentary, lightly active, moderately active, or very active",
    )
    dietary_restrictions: Optional[str] = Field(default=None, description="FitMax: dietary restrictions text")


class StopScheduleInput(BaseModel):
    maxx_id: str = Field(description="skinmax, heightmax, hairmax, fitmax, bonemax")


class UpdateScheduleContextInput(BaseModel):
    key: str = Field(description="Context key, e.g. outside_today, wake_time")
    value: str = Field(description="Context value")


class LogCheckInInput(BaseModel):
    workout_done: Optional[bool] = Field(default=None)
    missed: Optional[bool] = Field(default=None)
    sleep_hours: Optional[float] = Field(default=None)
    calories: Optional[int] = Field(default=None)
    mood: Optional[str] = Field(default=None)
    injury_area: Optional[str] = Field(default=None)
    injury_note: Optional[str] = Field(default=None)


class SetCoachingModeInput(BaseModel):
    mode: str = Field(description="hardcore=brutal accountability, gentle=supportive, default=direct style")


class GetTodayTasksInput(BaseModel):
    pass


class GetModuleInfoInput(BaseModel):
    module: str = Field(description="skinmax, hairmax, fitmax, bonemax, heightmax")
    topic: Optional[str] = Field(default=None, description="Optional sub-topic, e.g. 'minoxidil', 'mewing'")


class RecommendProductInput(BaseModel):
    module: str = Field(description="skinmax, hairmax, fitmax, bonemax, heightmax")
    concern: str = Field(description="User's concern, e.g. 'acne', 'thinning', 'fat loss'")


# ---------------------------------------------------------------------------
# Stub functions — schema only, execution stays in lc_agent.py closures
# ---------------------------------------------------------------------------

def _stub(*args, **kwargs) -> str:
    return ""


# ---------------------------------------------------------------------------
# CHAT_TOOLS — the single authoritative list of tool definitions
# ---------------------------------------------------------------------------

CHAT_TOOLS: list[StructuredTool] = [
    StructuredTool(
        name="modify_schedule",
        description="Modifies the user's active schedule from natural language. Only when they want calendar/task changes.",
        args_schema=ModifyScheduleInput,
        func=_stub,
        coroutine=None,
    ),
    StructuredTool(
        name="generate_maxx_schedule",
        description="Generate a personalised maxx schedule after onboarding fields are collected.",
        args_schema=GenerateMaxxScheduleInput,
        func=_stub,
        coroutine=None,
    ),
    StructuredTool(
        name="stop_schedule",
        description="Deactivate a module schedule when the user wants to stop it.",
        args_schema=StopScheduleInput,
        func=_stub,
        coroutine=None,
    ),
    StructuredTool(
        name="update_schedule_context",
        description="Store schedule habit context e.g. outside_today, wake_time.",
        args_schema=UpdateScheduleContextInput,
        func=_stub,
        coroutine=None,
    ),
    StructuredTool(
        name="log_check_in",
        description=(
            "Log check-in data ONLY when user explicitly reports their day — e.g. 'i did my workout', "
            "'slept 7 hours', 'ate 1800 cals', 'missed today'. Do NOT call for questions or casual chat."
        ),
        args_schema=LogCheckInInput,
        func=_stub,
        coroutine=None,
    ),
    StructuredTool(
        name="set_coaching_mode",
        description=(
            "Set coaching intensity. Call when user says 'be harder on me', 'go easy', "
            "'tough love', 'be more chill', 'back to normal'."
        ),
        args_schema=SetCoachingModeInput,
        func=_stub,
        coroutine=None,
    ),
    StructuredTool(
        name="get_today_tasks",
        description=(
            "Returns today's task list. ONLY call when user explicitly asks what tasks or schedule "
            "they have today ('what do i have today', 'show my schedule'). Do NOT call for greetings, "
            "general questions, or when schedule info is already in context."
        ),
        args_schema=GetTodayTasksInput,
        func=_stub,
        coroutine=None,
    ),
    StructuredTool(
        name="get_module_info",
        description="Fetch protocol/coaching reference for a module. Use when user asks a detailed how-to or protocol question about a specific module.",
        args_schema=GetModuleInfoInput,
        func=_stub,
        coroutine=None,
    ),
    StructuredTool(
        name="recommend_product",
        description="Get product/ingredient recommendations for a module and concern. Use when user asks what to buy or what products to use.",
        args_schema=RecommendProductInput,
        func=_stub,
        coroutine=None,
    ),
]

CHAT_TOOL_NAMES: frozenset[str] = frozenset(t.name for t in CHAT_TOOLS)
