"""
Load LLM / coaching prompts from S3 with in-repo string fallbacks.

S3 layout (either extension works; .md tried first):
  s3://{PROMPTS_S3_BUCKET}/{PROMPTS_S3_PREFIX}/{key}.md
  s3://{PROMPTS_S3_BUCKET}/{PROMPTS_S3_PREFIX}/{key}.txt

If PROMPTS_S3_BUCKET is empty, fallbacks are always used (no S3 calls).

Keys (must match uploaded object names without extension):
  face_analysis_system, umax_triple_system, triple_full_system, max_chat_system,
  bonemax_new_schedule_system, schedule_generation, schedule_adaptation, maxx_schedule,
  coaching_memory_compress, coaching_tone_detect, coaching_fitmax_check_in,
  coaching_check_in_general, coaching_bedtime,
  Per maxx (notification engine — coaching snippet, full reference md, json directives):
  skinmax_*, bonemax_*, heightmax_*, hairmax_*, fitmax_* with suffixes
  _coaching_reference, _notification_engine_reference, _json_directives,
  langgraph_validate_images, langgraph_analyze_face_metrics, langgraph_improvements
"""

from __future__ import annotations

import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from config import settings

logger = logging.getLogger(__name__)

_CACHE: dict[str, str] = {}


def _s3_client():
    region = (
        (getattr(settings, "prompts_s3_region", None) or "").strip()
        or (settings.aws_s3_region or "").strip()
        or "us-east-1"
    )
    kwargs: dict = {"region_name": region}
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.client("s3", **kwargs)


def resolve_prompt(key: str, fallback: str) -> str:
    """
    Return prompt text from S3 if configured and object exists; otherwise fallback.
    Successful S3 bodies are cached for the process lifetime.
    Missing bucket, missing object, or errors: return fallback (not cached when bucket is set,
    so uploading a new object takes effect without restart once the failed key is retried —
    note: successful fallbacks when bucket is unset are cached).
    """
    if key in _CACHE:
        return _CACHE[key]

    bucket = (settings.prompts_s3_bucket or "").strip()
    if not bucket:
        _CACHE[key] = fallback
        return fallback

    raw_prefix = settings.prompts_s3_prefix
    if raw_prefix is None:
        prefix = "prompts/prod"
    else:
        prefix = (raw_prefix or "").strip().strip("/")
    client = _s3_client()

    for ext in (".md", ".txt"):
        object_key = f"{prefix}/{key}{ext}" if prefix else f"{key}{ext}"
        try:
            resp = client.get_object(Bucket=bucket, Key=object_key)
            raw = resp["Body"].read().decode("utf-8")
            text = raw.lstrip("\ufeff").strip()
            if text:
                logger.info("Loaded prompt %s from s3://%s/%s", key, bucket, object_key)
                _CACHE[key] = text
                return text
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code", "")
            if code not in ("404", "NoSuchKey", "NotFound"):
                logger.warning(
                    "S3 prompt load failed key=%s object=%s error=%s — using fallback",
                    key,
                    object_key,
                    code or str(e),
                )
        except Exception as e:
            logger.warning("S3 prompt load error key=%s: %s — using fallback", key, e)

    return fallback


def clear_prompt_cache() -> None:
    """Test / reload hooks."""
    _CACHE.clear()


# Stable key constants for callers and AWS uploads
class PromptKey:
    FACE_ANALYSIS_SYSTEM = "face_analysis_system"
    UMAX_TRIPLE_SYSTEM = "umax_triple_system"
    TRIPLE_FULL_SYSTEM = "triple_full_system"
    MAX_CHAT_SYSTEM = "max_chat_system"
    BONEMAX_NEW_SCHEDULE_SYSTEM = "bonemax_new_schedule_system"
    SCHEDULE_GENERATION = "schedule_generation"
    SCHEDULE_ADAPTATION = "schedule_adaptation"
    MAXX_SCHEDULE = "maxx_schedule"
    COACHING_MEMORY_COMPRESS = "coaching_memory_compress"
    COACHING_TONE_DETECT = "coaching_tone_detect"
    COACHING_FITMAX_CHECK_IN = "coaching_fitmax_check_in"
    COACHING_CHECK_IN_GENERAL = "coaching_check_in_general"
    COACHING_BEDTIME = "coaching_bedtime"
    # Maxx notification engines (schedule + coaching context)
    SKINMAX_COACHING_REFERENCE = "skinmax_coaching_reference"
    SKINMAX_NOTIFICATION_ENGINE_REFERENCE = "skinmax_notification_engine_reference"
    SKINMAX_JSON_DIRECTIVES = "skinmax_json_directives"
    BONEMAX_COACHING_REFERENCE = "bonemax_coaching_reference"
    BONEMAX_NOTIFICATION_ENGINE_REFERENCE = "bonemax_notification_engine_reference"
    BONEMAX_JSON_DIRECTIVES = "bonemax_json_directives"
    HEIGHTMAX_COACHING_REFERENCE = "heightmax_coaching_reference"
    HEIGHTMAX_NOTIFICATION_ENGINE_REFERENCE = "heightmax_notification_engine_reference"
    HEIGHTMAX_JSON_DIRECTIVES = "heightmax_json_directives"
    HAIRMAX_COACHING_REFERENCE = "hairmax_coaching_reference"
    HAIRMAX_NOTIFICATION_ENGINE_REFERENCE = "hairmax_notification_engine_reference"
    HAIRMAX_JSON_DIRECTIVES = "hairmax_json_directives"
    FITMAX_COACHING_REFERENCE = "fitmax_coaching_reference"
    FITMAX_NOTIFICATION_ENGINE_REFERENCE = "fitmax_notification_engine_reference"
    FITMAX_JSON_DIRECTIVES = "fitmax_json_directives"
    # LangGraph face workflow
    LANGGRAPH_VALIDATE_IMAGES = "langgraph_validate_images"
    LANGGRAPH_ANALYZE_FACE_METRICS = "langgraph_analyze_face_metrics"
    LANGGRAPH_IMPROVEMENTS = "langgraph_improvements"
