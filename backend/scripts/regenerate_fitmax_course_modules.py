"""
Rewrite services/fitmax_course_modules.py from mobile/features/fitmax/modules.full.ts
(authoritative copy). Requires Node + mobile deps (npx tsx).

Usage:
    cd backend
    python scripts/regenerate_fitmax_course_modules.py

Embeds data as base64 + json.loads so content never breaks Python syntax (repr() can fail on
certain backslashes in long strings).
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
MOBILE = REPO / "mobile"
OUT = BACKEND / "services" / "fitmax_course_modules.py"

TS_EVAL = r"""
import { FITMAX_MODULES_FULL } from './features/fitmax/modules.full.ts';
console.log(JSON.stringify(FITMAX_MODULES_FULL));
"""


def main() -> None:
    if not MOBILE.is_dir():
        print("mobile/ not found next to backend/; abort.", file=sys.stderr)
        sys.exit(1)

    cmd = 'npx --yes tsx -e "import { FITMAX_MODULES_FULL } from \'./features/fitmax/modules.full.ts\'; console.log(JSON.stringify(FITMAX_MODULES_FULL));"'
    r = subprocess.run(
        cmd,
        cwd=str(MOBILE),
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if r.returncode != 0:
        print(r.stderr or r.stdout, file=sys.stderr)
        sys.exit(r.returncode)
    raw = (r.stdout or "").strip()
    if not raw.startswith("["):
        print("Unexpected tsx output (expected JSON array):", raw[:200], file=sys.stderr)
        sys.exit(1)
    mods = json.loads(raw)
    payload = json.dumps(mods, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    b64 = base64.standard_b64encode(payload).decode("ascii")

    py = f'''# Fitmax course modules — generated from mobile/features/fitmax/modules.full.ts
# Regenerate: python scripts/regenerate_fitmax_course_modules.py
from __future__ import annotations

import base64
import json
from typing import Any

_B64 = {b64!r}

FITMAX_COURSE_MODULES: list[dict[str, Any]] = json.loads(
    base64.standard_b64decode(_B64.encode("ascii")).decode("utf-8")
)
'''
    OUT.write_text(py, encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes, {len(mods)} modules)")


if __name__ == "__main__":
    main()
