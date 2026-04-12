"""
Direct Apple Push Notification service (HTTP/2, JWT auth).
https://developer.apple.com/documentation/usernotifications/setting_up_a_remote_notification_server
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any, Optional

import httpx
import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from config import settings

logger = logging.getLogger(__name__)

_APNS_SANDBOX = "https://api.sandbox.push.apple.com"
_APNS_PRODUCTION = "https://api.push.apple.com"


def _load_private_key(pem_or_b64: str):
    raw = (pem_or_b64 or "").strip()
    if not raw:
        raise ValueError("empty APNs key")
    if "\\n" in raw:
        raw = raw.replace("\\n", "\n")
    if not raw.startswith("-----"):
        try:
            raw = base64.b64decode(raw).decode("utf-8").strip()
        except Exception:
            raise ValueError("APNs key is not valid PEM or base64")
    if "-----BEGIN" in raw and "\n" not in raw:
        raw = raw.replace("-----BEGIN PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----\n")
        raw = raw.replace("-----END PRIVATE KEY-----", "\n-----END PRIVATE KEY-----\n")
    return serialization.load_pem_private_key(
        raw.encode("utf-8"),
        password=None,
        backend=default_backend(),
    )


def _apns_jwt() -> str:
    key = _load_private_key(settings.apns_auth_key_p8)
    return jwt.encode(
        {"iss": settings.apns_team_id, "iat": int(time.time())},
        key,
        algorithm="ES256",
        headers={"kid": settings.apns_key_id, "alg": "ES256"},
    )


def apns_configured() -> bool:
    return bool(
        settings.apns_auth_key_p8.strip()
        and settings.apns_key_id.strip()
        and settings.apns_team_id.strip()
        and settings.apns_bundle_id.strip()
    )


async def send_apns_alert(
    device_token_hex: str,
    title: str,
    body: str,
    *,
    badge: Optional[int] = None,
    custom: Optional[dict[str, Any]] = None,
) -> tuple[bool, Optional[int]]:
    """
    Send alert push. Returns (success, status_code).
    410 / BadDeviceToken → caller should clear stored token.
    """
    if not apns_configured():
        logger.debug("APNs not configured; skip push")
        return False, None
    token_hex = (device_token_hex or "").strip().replace(" ", "")
    if not token_hex:
        return False, None

    base = _APNS_SANDBOX if settings.apns_use_sandbox else _APNS_PRODUCTION
    url = f"{base}/3/device/{token_hex}"

    try:
        auth = _apns_jwt()
    except Exception as e:
        logger.error("APNs JWT build failed: %s", e)
        return False, None

    aps: dict[str, Any] = {"alert": {"title": title, "body": body}, "sound": "default"}
    if badge is not None:
        aps["badge"] = badge
    payload: dict[str, Any] = {"aps": aps}
    if custom:
        for k, v in custom.items():
            if k != "aps":
                payload[k] = v

    headers = {
        "authorization": f"bearer {auth}",
        "apns-topic": settings.apns_bundle_id,
        "apns-push-type": "alert",
        "apns-priority": "10",
    }

    try:
        async with httpx.AsyncClient(http2=True, timeout=30.0) as client:
            r = await client.post(url, headers=headers, content=json.dumps(payload))
    except Exception as e:
        logger.warning("APNs request failed (%s): %s", type(e).__name__, e)
        return False, None

    if r.status_code == 200:
        return True, 200

    logger.warning("APNs HTTP %s: %s", r.status_code, (r.text or "")[:500])
    return False, r.status_code


def apns_response_should_invalidate_token(status_code: Optional[int]) -> bool:
    return status_code in (400, 410)
