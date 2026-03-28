"""
Blocking LLM calls for use inside asyncio.to_thread (JSON schedule gen, coaching text).
"""

from config import settings
from services.llm_provider import use_openai


def sync_llm_json_response(prompt: str) -> str:
    """Return raw JSON string from the configured provider."""
    if use_openai():
        from openai import OpenAI

        key = (settings.openai_api_key or "").strip()
        if not key:
            return "{}"
        client = OpenAI(api_key=key)
        model = (settings.openai_model or "gpt-4o-mini").strip()
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return r.choices[0].message.content or "{}"

    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(response_mime_type="application/json"),
    )
    return response.text


def sync_llm_plain_text(prompt: str) -> str:
    """Return plain text from the configured provider."""
    if use_openai():
        from openai import OpenAI

        key = (settings.openai_api_key or "").strip()
        if not key:
            return ""
        client = OpenAI(api_key=key)
        model = (settings.openai_model or "gpt-4o-mini").strip()
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return (r.choices[0].message.content or "").strip()

    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)
    resp = model.generate_content(prompt)
    return (resp.text or "").strip()
