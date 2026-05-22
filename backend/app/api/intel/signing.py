"""
Endpoints related to Ed25519 report signing.

Two routers are exposed:

* :data:`public_router` — anonymous, mounted under
  ``/api/v1/public/signing``. Lets external clients fetch the active
  public key and verify a signature server-side. No PII or report
  body crosses this boundary, only signed canonical bytes.

* :data:`admin_router` — mounted under
  ``/api/v1/classified/admin/signing`` and protected by the
  classified router's MFA / clearance dependency. Used for key
  rotation.

Each report also exposes ``GET /reports/{id}/signature`` from inside
:mod:`app.api.endpoints.reports`.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.intel.deps import get_current_admin, get_db
from app.core.config import settings
from app.db.models.intel.user import User, RoleEnum
from app.services.intel.audit import audit_service
from app.services.intel.signing import (
    SigningUnavailableError,
    report_signer,
)


logger = logging.getLogger(__name__)

public_router = APIRouter()
admin_router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PublicKeyResponse(BaseModel):
    public_key_pem: str
    fingerprint: str
    algorithm: str = "Ed25519"


class VerifyRequest(BaseModel):
    canonical_payload: str = Field(
        ...,
        description="UTF-8 string of the canonical JSON payload as built "
        "by ReportSigner.canonical_payload. Will be encoded to bytes "
        "before verification.",
    )
    signature: str = Field(
        ..., description="Base64 blob produced by ReportSigner.sign."
    )


class VerifyResponse(BaseModel):
    valid: bool
    fingerprint: str


class RotateRequest(BaseModel):
    """Optional body for ``POST /signing/rotate``.

    ``reason`` is captured for forensics — it lands in the audit log
    metadata so a future investigator can map *why* the key rotated.
    Trimmed to 500 chars to keep audit rows bounded.
    """

    reason: Optional[str] = Field(default=None, max_length=500)


class RotateResponse(BaseModel):
    new_fingerprint: str
    archived_old_fingerprint: Optional[str]
    public_key_pem: str


# ---------------------------------------------------------------------------
# Public — unauthenticated
# ---------------------------------------------------------------------------


@public_router.get("/pubkey", response_model=PublicKeyResponse)
async def get_public_key() -> PublicKeyResponse:
    """Return the active signing public key in PEM PKCS#8.

    Returning this anonymously is by design: signature verification
    is supposed to be performed by any party that has the public
    bytes. Distributing the key over an authenticated channel buys
    nothing because the key itself is non-secret.
    """
    if not report_signer.available:
        # Even outside state-grade mode, we surface the disabled state
        # explicitly rather than serve an ephemeral key without
        # warning. Ephemeral keys still have a fingerprint and are
        # returned with ``available=True``; this only fires when the
        # signer marked itself unavailable.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signing service unavailable: no key loaded",
        )
    return PublicKeyResponse(
        public_key_pem=report_signer.public_key_pem,
        fingerprint=report_signer.fingerprint,
        algorithm="Ed25519",
    )


@public_router.post("/verify", response_model=VerifyResponse)
async def verify_signature(body: VerifyRequest) -> VerifyResponse:
    """Verify a caller-supplied canonical payload + signature pair.

    Stateless: the server does not need the report id and never
    touches the database. The verifier produces canonical bytes
    locally (or with the same algorithm in another language) and
    POSTs them here for an authoritative answer.
    """
    if not report_signer.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signing service unavailable",
        )
    try:
        payload_bytes = body.canonical_payload.encode("utf-8")
    except Exception:
        return VerifyResponse(valid=False, fingerprint=report_signer.fingerprint)
    valid = report_signer.verify_payload(payload_bytes, body.signature)
    return VerifyResponse(valid=valid, fingerprint=report_signer.fingerprint)


# ---------------------------------------------------------------------------
# Admin — key rotation
# ---------------------------------------------------------------------------


@admin_router.post("/rotate", response_model=RotateResponse)
async def rotate_signing_key(
    body: RotateRequest = Body(default_factory=RotateRequest),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> RotateResponse:
    """Generate a new Ed25519 keypair and replace the active one.

    The old public key is archived under
    ``<priv_dir>/archive/<old_fingerprint>.pem`` so historical
    reports that were signed with it remain verifiable by clients
    that fetch the archived key explicitly.

    Audit emits ``signing.key.rotated`` with the new and archived
    fingerprints, never the private bytes.
    """
    if admin.role != RoleEnum.admin:
        # Belt-and-braces: classified router already gates this on
        # MFA + clearance, but rotation MUST also require admin role.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to rotate the signing key",
        )

    archive_dir: Optional[Path] = None
    if settings.SIGNING_PUBLIC_KEY_PATH:
        archive_dir = Path(settings.SIGNING_PUBLIC_KEY_PATH).parent / "archive"

    try:
        new_fp, archived_fp, pem = report_signer.rotate(archive_dir=archive_dir)
    except Exception as exc:  # noqa: BLE001
        logger.error("Signing rotate failed: %s", exc.__class__.__name__)
        # Audit the failure too (no secret material in metadata).
        try:
            await audit_service.record(
                db,
                event_type="signing.key.rotate_failed",
                actor_user_id=admin.id,
                outcome="error",
                metadata={"error_class": exc.__class__.__name__},
            )
            await db.commit()
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Key rotation failed",
        )

    # Reason is forensics-grade metadata: stored in audit so future
    # investigations can map *why* a key rotated. Bounded to 500 chars
    # by RotateRequest validation.
    reason_clean = (body.reason or "").strip() or None
    await audit_service.record(
        db,
        event_type="signing.key.rotated",
        actor_user_id=admin.id,
        outcome="success",
        metadata={
            "new_fingerprint": new_fp,
            "archived_old_fingerprint": archived_fp,
            "ephemeral": report_signer.ephemeral,
            "reason": reason_clean,
        },
    )
    await db.commit()

    return RotateResponse(
        new_fingerprint=new_fp,
        archived_old_fingerprint=archived_fp,
        public_key_pem=pem,
    )


__all__ = ["public_router", "admin_router"]
