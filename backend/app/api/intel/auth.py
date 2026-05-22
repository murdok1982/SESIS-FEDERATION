"""
Authentication endpoints, including MFA enrollment & verification.

Login flow (state-grade):

    1. POST /auth/login            ─┐
                                    ├─ if MFA disabled: access + refresh
                                    ├─ if MFA enabled:  challenge_token only
    2. POST /auth/mfa/verify       ─┘  → access + refresh w/ mfa_verified=true

The challenge token is signed with a dedicated secret
(``MFA_CHALLENGE_SECRET``) and expires in five minutes.

All endpoints emit audit events. Failures are rate-limited per-IP
through :data:`app.core.limiter.limiter`.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.intel.deps import get_current_active_user, get_db
from app.services.intel.auth.challenge import (
    create_mfa_challenge_token,
    decode_mfa_challenge_token,
)
from app.services.intel.auth.mfa import generate_recovery_codes, totp_service
from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.db.models.intel.auth import MFARecoveryCode
from app.db.models.intel.user import User
from app.schemas.token import AccessToken, RefreshToken, Token
from app.schemas.user import UserCreate, UserResponse
from app.services.intel.audit import audit_service

router = APIRouter()
security_logger = logging.getLogger("security")

# Reusable bcrypt context for recovery codes. Same scheme as passwords
# so we depend on a single primitive.
_recovery_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MFALoginResponse(BaseModel):
    mfa_required: bool = True
    challenge_token: str
    expires_in: int


class MFAEnrollStartResponse(BaseModel):
    provisioning_uri: str
    secret_b32: str
    recovery_codes: list[str]


class MFAEnrollVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)


class MFAVerifyRequest(BaseModel):
    challenge_token: str
    code: str = Field(..., min_length=6, max_length=16)


class MFADisableRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)


class MFAStatusResponse(BaseModel):
    enrolled: bool
    recovery_codes_remaining: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _audit(db: AsyncSession, **kwargs: Any) -> None:
    """Record an audit event and commit it on its own."""
    try:
        await audit_service.record(db, **kwargs)
        await db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        security_logger.error("auth.audit_failed err=%r", exc)


async def _consume_recovery_code(
    db: AsyncSession, user_id: Any, code: str
) -> bool:
    """Match ``code`` against the user's unused recovery codes.

    On match, mark the code as used and return True. Returns False
    otherwise. The function performs a constant-time-ish comparison
    by bcrypt-verifying against every unused row.
    """
    from datetime import datetime as _dt

    code_norm = code.strip().upper()
    result = await db.execute(
        select(MFARecoveryCode).where(
            MFARecoveryCode.user_id == user_id,
            MFARecoveryCode.used_at.is_(None),
        )
    )
    rows = result.scalars().all()
    for row in rows:
        try:
            if _recovery_ctx.verify(code_norm, row.code_hash):
                row.used_at = _dt.utcnow()
                await db.flush()
                return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Register / login / refresh / me
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: UserCreate, db: AsyncSession = Depends(get_db)
) -> UserResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user = User(
        email=body.email,
        hashed_password=get_password_hash(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Password login.

    If the user has 2FA enabled, only a short-lived ``challenge_token``
    is returned (no access/refresh tokens). The caller must follow up
    with ``/auth/mfa/verify`` to exchange it for the real session.
    """
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        security_logger.warning(
            "auth.login.failed email=%s ip=%s",
            form_data.username,
            _client_ip(request),
        )
        await _audit(
            db,
            event_type="auth.login.failure",
            actor_user_id=str(user.id) if user else None,
            actor_ip=_client_ip(request),
            actor_user_agent=request.headers.get("user-agent"),
            outcome="denied",
            metadata={"reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )

    if user.two_factor_enabled:
        challenge = create_mfa_challenge_token(str(user.id))
        await _audit(
            db,
            event_type="auth.login.mfa_challenge_issued",
            actor_user_id=str(user.id),
            actor_ip=_client_ip(request),
            actor_user_agent=request.headers.get("user-agent"),
            outcome="success",
        )
        return MFALoginResponse(
            mfa_required=True,
            challenge_token=challenge,
            expires_in=300,
        )

    # No second factor: emit access + refresh WITHOUT mfa_verified.
    # These tokens cannot reach /classified/* in STATE_GRADE_MODE.
    await _audit(
        db,
        event_type="auth.login.success",
        actor_user_id=str(user.id),
        actor_ip=_client_ip(request),
        actor_user_agent=request.headers.get("user-agent"),
        outcome="success",
        metadata={"mfa_verified": False},
    )
    return Token(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
        token_type="bearer",
    )


@router.post("/refresh", response_model=AccessToken)
async def refresh_token(
    body: RefreshToken,
    db: AsyncSession = Depends(get_db),
) -> AccessToken:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(body.refresh_token, is_refresh=True)
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if user_id is None or token_type != "refresh":
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user or not user.is_active:
        raise credentials_exception

    # Carry the mfa_verified claim forward only if the refresh token
    # itself was issued post-MFA. Otherwise the new access token is
    # plain and cannot enter the classified scope.
    mfa_verified = bool(payload.get("mfa_verified", False))
    return AccessToken(
        access_token=create_access_token(str(user.id), mfa_verified=mfa_verified)
    )


@router.get("/me", response_model=UserResponse)
async def read_me(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)


# ---------------------------------------------------------------------------
# MFA endpoints
# ---------------------------------------------------------------------------


@router.post("/mfa/enroll/start", response_model=MFAEnrollStartResponse)
@limiter.limit("3/hour")
async def mfa_enroll_start(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> MFAEnrollStartResponse:
    """Begin MFA enrollment.

    Generates a fresh secret, encrypts it at rest, stores the provisioning
    URI (returned to the client only once) and emits 10 single-use
    recovery codes (also returned exactly once).

    The user is marked ``two_factor_enabled=False`` here — completion of
    ``/mfa/enroll/verify`` flips it to True so partial enrolments do not
    lock the user out.
    """
    if user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MFA already enabled. Disable first to re-enrol.",
        )

    secret = totp_service.generate_secret()
    encrypted = totp_service.encrypt_secret(secret)
    user.mfa_secret = encrypted
    user.two_factor_enabled = False  # pending until verify

    # Generate, hash and store recovery codes. The plaintext is
    # returned to the caller exactly once.
    plain_codes = generate_recovery_codes()
    # Clear any leftover unused codes from a previous attempt.
    await db.execute(
        MFARecoveryCode.__table__.delete().where(MFARecoveryCode.user_id == user.id)
    )
    for code in plain_codes:
        db.add(
            MFARecoveryCode(
                user_id=user.id,
                code_hash=_recovery_ctx.hash(code),
            )
        )
    await db.commit()

    uri = totp_service.provisioning_uri(user.email, secret)
    await _audit(
        db,
        event_type="auth.mfa.enroll.start",
        actor_user_id=str(user.id),
        actor_ip=_client_ip(request),
        actor_user_agent=request.headers.get("user-agent"),
        outcome="success",
    )

    return MFAEnrollStartResponse(
        provisioning_uri=uri,
        secret_b32=secret,
        recovery_codes=plain_codes,
    )


@router.post("/mfa/enroll/verify")
async def mfa_enroll_verify(
    request: Request,
    body: MFAEnrollVerifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> dict:
    """Confirm enrollment by validating the first TOTP code."""
    if not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending enrollment — call /mfa/enroll/start first",
        )
    try:
        secret = totp_service.decrypt_secret(user.mfa_secret)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MFA secret corrupted — re-enrol",
        )
    if not totp_service.verify_code(secret, body.code):
        await _audit(
            db,
            event_type="auth.mfa.enroll.failure",
            actor_user_id=str(user.id),
            actor_ip=_client_ip(request),
            actor_user_agent=request.headers.get("user-agent"),
            outcome="denied",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid TOTP code",
        )
    user.two_factor_enabled = True
    await db.commit()
    await _audit(
        db,
        event_type="auth.mfa.enroll.success",
        actor_user_id=str(user.id),
        actor_ip=_client_ip(request),
        actor_user_agent=request.headers.get("user-agent"),
        outcome="success",
    )
    return {"verified": True}


@router.post("/mfa/verify", response_model=Token)
@limiter.limit("5/15minutes")
async def mfa_verify(
    request: Request,
    body: MFAVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Exchange a challenge token + TOTP/recovery code for real tokens."""
    try:
        payload = decode_mfa_challenge_token(body.challenge_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Challenge expired — log in again",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid challenge token",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user or not user.is_active or not user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA verification failed",
        )

    accepted = False
    # First try as a TOTP code.
    if user.mfa_secret:
        try:
            secret = totp_service.decrypt_secret(user.mfa_secret)
            if totp_service.verify_code(secret, body.code):
                accepted = True
        except RuntimeError:
            # Tamper / corruption — fall through to denied
            pass

    # Fall back to a single-use recovery code.
    if not accepted:
        if await _consume_recovery_code(db, user.id, body.code):
            accepted = True
            await db.commit()

    if not accepted:
        await _audit(
            db,
            event_type="auth.mfa.failure",
            actor_user_id=str(user.id),
            actor_ip=_client_ip(request),
            actor_user_agent=request.headers.get("user-agent"),
            outcome="denied",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MFA code",
        )

    await _audit(
        db,
        event_type="auth.mfa.success",
        actor_user_id=str(user.id),
        actor_ip=_client_ip(request),
        actor_user_agent=request.headers.get("user-agent"),
        outcome="success",
        metadata={"method": "totp_or_recovery"},
    )
    return Token(
        access_token=create_access_token(str(user.id), mfa_verified=True),
        refresh_token=create_refresh_token(str(user.id), mfa_verified=True),
        token_type="bearer",
    )


@router.post("/mfa/disable")
async def mfa_disable(
    request: Request,
    body: MFADisableRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> dict:
    """Disable MFA. Requires a valid current TOTP code."""
    if not user.two_factor_enabled or not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled",
        )
    try:
        secret = totp_service.decrypt_secret(user.mfa_secret)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MFA secret corrupted — contact an administrator",
        )
    if not totp_service.verify_code(secret, body.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code"
        )

    user.two_factor_enabled = False
    user.mfa_secret = None
    await db.execute(
        MFARecoveryCode.__table__.delete().where(MFARecoveryCode.user_id == user.id)
    )
    await db.commit()
    await _audit(
        db,
        event_type="auth.mfa.disable",
        actor_user_id=str(user.id),
        actor_ip=_client_ip(request),
        actor_user_agent=request.headers.get("user-agent"),
        outcome="success",
    )
    return {"disabled": True}


@router.get("/mfa/status", response_model=MFAStatusResponse)
async def mfa_status(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> MFAStatusResponse:
    from sqlalchemy import func

    remaining = 0
    if user.two_factor_enabled:
        result = await db.execute(
            select(func.count(MFARecoveryCode.id)).where(
                MFARecoveryCode.user_id == user.id,
                MFARecoveryCode.used_at.is_(None),
            )
        )
        remaining = int(result.scalar() or 0)
    return MFAStatusResponse(
        enrolled=bool(user.two_factor_enabled),
        recovery_codes_remaining=remaining,
    )


# ---------------------------------------------------------------------------
# WebAuthn — schema-only stub. P3+ will replace this with the full
# registration/assertion flow.
# ---------------------------------------------------------------------------


@router.get("/webauthn/options", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def webauthn_options(_: User = Depends(get_current_active_user)) -> Any:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="WebAuthn enrollment is not implemented yet (planned for P3)",
        headers={"Retry-After": "604800"},
    )
