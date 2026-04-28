"""HMAC-signed cookie sessions.

Cookie format: <base64-payload>.<hex-signature>
Payload (JSON): {"exp": <unix_ts>}
Signature: HMAC-SHA256(secret, payload).hex
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import HTTPException, Request, status


class SessionInvalidError(Exception):
    pass


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(secret: str, payload_b64: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def make_session_cookie(secret: str, ttl_sec: int) -> str:
    payload = {"exp": int(time.time()) + ttl_sec}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)
    sig = _sign(secret, payload_b64)
    return f"{payload_b64}.{sig}"


def verify_session_cookie(secret: str, cookie: Optional[str]) -> dict:
    if not cookie or "." not in cookie:
        raise SessionInvalidError("malformed cookie")
    payload_b64, sig = cookie.rsplit(".", 1)
    expected = _sign(secret, payload_b64)
    if not hmac.compare_digest(sig, expected):
        raise SessionInvalidError("bad signature")
    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        raise SessionInvalidError("malformed payload")
    if "exp" not in payload or int(payload["exp"]) < int(time.time()):
        raise SessionInvalidError("expired")
    return payload


def verify_password(expected: str, given: str) -> bool:
    return hmac.compare_digest(expected.encode("utf-8"), given.encode("utf-8"))


def require_session_factory(secret: str, cookie_name: str = "yig_session"):
    """Return a FastAPI dependency that enforces a valid session cookie."""

    def dependency(request: Request) -> dict:
        cookie = request.cookies.get(cookie_name)
        try:
            return verify_session_cookie(secret, cookie)
        except SessionInvalidError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
                headers={"WWW-Authenticate": 'Cookie realm="yig"'},
            )

    return dependency
