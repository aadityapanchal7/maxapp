"""
Export LLM prompt bodies to .md files for uploading to S3.

Includes: Gemini chat/scan/schedule prompts, coaching SMS prompts, all maxx
notification-engine snippets (+ full reference markdown), and LangGraph face
workflow prompts.

Run from backend root:
  python scripts/export_s3_prompts.py

Or with a custom output directory:
  python scripts/export_s3_prompts.py --out ./my-upload-folder

Upload files to:
  s3://<PROMPTS_S3_BUCKET>/<PROMPTS_S3_PREFIX>/<key>.md
If prompts_s3_prefix is unset, default is prompts/prod (see config).
"""

from __future__ import annotations

import argparse
import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from services.bonemax_chat_prompt import BONEMAX_NEW_SCHEDULE_SYSTEM_PROMPT
from services.bonemax_notification_engine import (
    BONEMAX_COACHING_REFERENCE,
    BONEMAX_JSON_DIRECTIVES,
    BONEMAX_NOTIFICATION_ENGINE_REFERENCE,
)
from services.coaching_service import (
    _COACHING_BEDTIME_FALLBACK,
    _COACHING_CHECK_IN_GENERAL_FALLBACK,
    _COACHING_FITMAX_CHECK_IN_FALLBACK,
    _COACHING_MEMORY_COMPRESS_FALLBACK,
    _COACHING_TONE_DETECT_FALLBACK,
)
from services.fitmax_notification_engine import (
    FITMAX_COACHING_REFERENCE,
    FITMAX_JSON_DIRECTIVES,
    FITMAX_NOTIFICATION_ENGINE_REFERENCE,
)
from services.langgraph_face_prompts import (
    LANGGRAPH_ANALYZE_FACE_METRICS_FALLBACK,
    LANGGRAPH_IMPROVEMENTS_FALLBACK,
    LANGGRAPH_VALIDATE_IMAGES_FALLBACK,
)
from services.gemini_service import (
    FACE_ANALYSIS_SYSTEM_PROMPT,
)
from services.prompt_constants import (
    MAX_CHAT_SYSTEM_PROMPT,
    TRIPLE_FULL_SYSTEM_PROMPT,
    UMAX_TRIPLE_SYSTEM_PROMPT,
)
from services.hairmax_notification_engine import (
    HAIRMAX_COACHING_REFERENCE,
    HAIRMAX_JSON_DIRECTIVES,
    HAIRMAX_NOTIFICATION_ENGINE_REFERENCE,
)
from services.heightmax_notification_engine import (
    HEIGHTMAX_COACHING_REFERENCE,
    HEIGHTMAX_JSON_DIRECTIVES,
    HEIGHTMAX_NOTIFICATION_ENGINE_REFERENCE,
)
from services.schedule_service import (
    MAXX_SCHEDULE_PROMPT,
    SCHEDULE_ADAPTATION_PROMPT,
    SCHEDULE_GENERATION_PROMPT,
)
from services.skinmax_notification_engine import (
    SKINMAX_COACHING_REFERENCE,
    SKINMAX_JSON_DIRECTIVES,
    SKINMAX_NOTIFICATION_ENGINE_REFERENCE,
)

_PROMPTS: dict[str, str] = {
    "face_analysis_system": FACE_ANALYSIS_SYSTEM_PROMPT,
    "umax_triple_system": UMAX_TRIPLE_SYSTEM_PROMPT,
    "triple_full_system": TRIPLE_FULL_SYSTEM_PROMPT,
    "max_chat_system": MAX_CHAT_SYSTEM_PROMPT,
    "bonemax_new_schedule_system": BONEMAX_NEW_SCHEDULE_SYSTEM_PROMPT,
    "schedule_generation": SCHEDULE_GENERATION_PROMPT,
    "schedule_adaptation": SCHEDULE_ADAPTATION_PROMPT,
    "maxx_schedule": MAXX_SCHEDULE_PROMPT,
    "coaching_memory_compress": _COACHING_MEMORY_COMPRESS_FALLBACK,
    "coaching_tone_detect": _COACHING_TONE_DETECT_FALLBACK,
    "coaching_fitmax_check_in": _COACHING_FITMAX_CHECK_IN_FALLBACK,
    "coaching_check_in_general": _COACHING_CHECK_IN_GENERAL_FALLBACK,
    "coaching_bedtime": _COACHING_BEDTIME_FALLBACK,
    # Notification engines (schedule generation + coaching context)
    "skinmax_coaching_reference": SKINMAX_COACHING_REFERENCE,
    "skinmax_notification_engine_reference": SKINMAX_NOTIFICATION_ENGINE_REFERENCE,
    "skinmax_json_directives": SKINMAX_JSON_DIRECTIVES,
    "bonemax_coaching_reference": BONEMAX_COACHING_REFERENCE,
    "bonemax_notification_engine_reference": BONEMAX_NOTIFICATION_ENGINE_REFERENCE,
    "bonemax_json_directives": BONEMAX_JSON_DIRECTIVES,
    "heightmax_coaching_reference": HEIGHTMAX_COACHING_REFERENCE,
    "heightmax_notification_engine_reference": HEIGHTMAX_NOTIFICATION_ENGINE_REFERENCE,
    "heightmax_json_directives": HEIGHTMAX_JSON_DIRECTIVES,
    "hairmax_coaching_reference": HAIRMAX_COACHING_REFERENCE,
    "hairmax_notification_engine_reference": HAIRMAX_NOTIFICATION_ENGINE_REFERENCE,
    "hairmax_json_directives": HAIRMAX_JSON_DIRECTIVES,
    "fitmax_coaching_reference": FITMAX_COACHING_REFERENCE,
    "fitmax_notification_engine_reference": FITMAX_NOTIFICATION_ENGINE_REFERENCE,
    "fitmax_json_directives": FITMAX_JSON_DIRECTIVES,
    # LangGraph face pipeline
    "langgraph_validate_images": LANGGRAPH_VALIDATE_IMAGES_FALLBACK,
    "langgraph_analyze_face_metrics": LANGGRAPH_ANALYZE_FACE_METRICS_FALLBACK,
    "langgraph_improvements": LANGGRAPH_IMPROVEMENTS_FALLBACK,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export S3 prompt .md files from code constants.")
    parser.add_argument(
        "--out",
        default=os.path.join(_BACKEND_ROOT, "s3_prompts_upload"),
        help="Output directory (default: backend/s3_prompts_upload)",
    )
    args = parser.parse_args()
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    for name, body in _PROMPTS.items():
        path = os.path.join(out_dir, f"{name}.md")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        print(f"wrote {path} ({len(body)} chars)")

    print(f"\nDone: {len(_PROMPTS)} files -> {out_dir}")
    print("Upload each file to s3://<bucket>/<prefix>/<name>.md (filenames match PromptKey / keys above).")
    print("Note: langgraph_improvements.md uses {overall_score} and doubled {{ }} for JSON literals - keep that if you edit in S3.")


if __name__ == "__main__":
    main()
