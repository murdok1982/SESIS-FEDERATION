"""
Short-lived MFA challenge token.

Issued by ``/auth/login`` when the user has ``two_factor_enabled=True``.
The token carries only ``sub`` and ``type="mfa_challenge"`` plus a
five-minute expiry, and is signed with :data:`settings.MFA_CHALLENGE_SECRET`
(separate from the access / refresh JWT secrets).

The client then presents this token + a fresh TOTP code (or recovery
code) to ``/auth/mfa/verify``, which mints the real access + refresh
tokens with the ``mfa_verified=true`` claim.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Union

import jwt

from app.core.config import settings


_CHALLENGE_TYPE = "mfa_challenge"
_ALGORITHM = "HS256"


def create_mfa_challenge_token(subject: Union[str, Any]) -> str:
    """Mint a short-lived MFA challenge JWT for ``subject`` (user id)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "type": _CHALLENGE_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=settings.MFA_CHALLENGE_TTL_SECONDS),
    }
    if not settings.MFA_CHALLENGE_SECRET:
        raise RuntimeError(
            "MFA_CHALLENGE_SECRET not configured — cannot mint challenge tokens."
        )
    return jwt.encode(payload, settings.MFA_CHALLENGE_SECRET, algorithm=_ALGORITHM)


def decode_mfa_challenge_token(token: str) -> dict:
    """Validate the challenge token and return its payload.

    Raises :class:`jwt.PyJWTError` (or subclasses) on expiry / bad
    signature / wrong type — callers MUST map them to HTTP 401.
    """
    if not settings.MFA_CHALLENGE_SECRET:
        raise RuntimeError("MFA_CHALLENGE_SECRET not configured")
    payload = jwt.decode(
        token,
        settings.MFA_CHALLENGE_SECRET,
        algorithms=[_ALGORITHM],
    )
    if payload.get("type") != _CHALLENGE_TYPE:
        raise jwt.InvalidTokenError("not a challenge token")
    return payload


__all__ = ["create_mfa_challenge_token", "decode_mfa_challenge_token"]
