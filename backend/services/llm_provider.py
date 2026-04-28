"""Which LLM backend to use: huggingface | gemini | openai | mistral."""

from config import settings

SUPPORTED_PROVIDERS = frozenset({"huggingface", "gemini", "openai", "mistral"})


def llm_provider() -> str:
    p = (settings.llm_provider or "huggingface").strip().lower()
    if p not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"LLM_PROVIDER={p!r} is not supported. "
            f"Choose from: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
        )
    return p


def use_huggingface() -> bool:
    return llm_provider() == "huggingface"


def use_openai() -> bool:
    return llm_provider() == "openai"


def use_mistral() -> bool:
    return llm_provider() == "mistral"


def use_gemini() -> bool:
    return llm_provider() == "gemini"
