"""Which LLM backend to use (Gemini vs OpenAI)."""

from config import settings


def llm_provider() -> str:
    return (settings.llm_provider or "gemini").strip().lower()


def use_openai() -> bool:
    return llm_provider() == "openai"
