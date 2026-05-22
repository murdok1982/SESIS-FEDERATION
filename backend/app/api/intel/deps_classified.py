"""
Dependencies for the ``/api/v1/classified`` mount point.

These dependencies layer extra checks on top of
``get_current_active_user`` so that no caller without MFA + a
non-PUBLIC clearance can reach the classified router.

NOTE: Full MFA enforcement (TOTP verification, attestation, ...) is
scheduled for P2. The current implementation accepts the
``mfa_verified`` claim from the access token when present and falls
back to ``two_factor_enabled`` on the user record. Endpoints behind
this dependency MUST be documented as gated.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.intel.deps import get_current_active_user, oauth2_scheme
from app.core.classification import ClassificationLevel, TLPMarker
from app.core.config import settings
from app.core.security import decode_token
from app.db.models.intel.user import User
from app.api.intel.deps import get_db

logger = logging.getLogger(__name__)


async def require_mfa_verified_user(
    token: str = Depends(oauth2_scheme),
    user: User = Depends(get_current_active_user),
) -> User:
    """Allow only authenticated users that satisfy the MFA gate.

    State-grade rule (STATE_GRADE_MODE=true): the access token MUST
    carry a ``mfa_verified=true`` claim issued by a fresh MFA exchange.
    The persistent ``user.two_factor_enabled`` flag is NEVER accepted
    as proof in state-grade mode — that flag only records enrollment,
    not a current session-bound second factor, so accepting it would
    let a stolen access token bypass MFA entirely.

    Development fallback (STATE_GRADE_MODE=false): if the claim is
    missing, accept ``user.two_factor_enabled`` as a STUB. Every use of
    the fallback emits a CRITICAL log line.

    TODO(P2): wire a real TOTP / WebAuthn exchange endpoint that
    re-mints an access token with the ``mfa_verified`` claim and a
    short TTL.
    """
    try:
        payload = decode_token(token, is_refresh=False)
    except Exception:  # pragma: no cover - get_current_active_user already validated
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials for classified scope",
        )

    mfa_claim = bool(payload.get("mfa_verified", False))

    if not mfa_claim:
        if settings.STATE_GRADE_MODE:
            # Fail closed. Persistent flags are not session-bound proof.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "MFA verification required (state-grade mode). "
                    "Re-authenticate through the MFA exchange."
                ),
            )
        if not bool(user.two_factor_enabled):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "MFA verification required to access the classified "
                    "scope. Enroll a second factor and re-authenticate."
                ),
            )
        logger.critical(
            "deps_classified.mfa_stub_fallback user=%s — accepting "
            "two_factor_enabled flag as session proof. "
            "DO NOT use in production.",
            getattr(user, "id", None),
        )

    clearance = ClassificationLevel(int(user.clearance_level or 0))
    if clearance < ClassificationLevel.RESTRICTED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient clearance for the classified scope",
        )

    return user


async def get_db_with_context(
    user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> AsyncSession:
    """Yield a session that has the caller's RLS context pushed."""
    await # set_user_context(
        session,
        clearance=int(user.clearance_level or 0),
        org_id=user.org_id,
    )
    return session
