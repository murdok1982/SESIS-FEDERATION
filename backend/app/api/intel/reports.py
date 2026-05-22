"""
Report endpoints — list, generate, retrieve, publish, signature.

Publication of a report is the moment at which it acquires a
detached Ed25519 signature and the ``signed_at`` /
``signature_fingerprint`` columns are filled in. If the signing
service is unavailable AND ``STATE_GRADE_MODE=true`` the publication
endpoint refuses the request with HTTP 503 so unsigned reports never
reach consumers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.agents.intel.osint import OSINTAgent
from app.agents.intel.synthesis import synthesis_agent
from app.api.intel.deps import (
    get_current_active_user,
    get_current_admin,
    get_current_institutional_user,
    get_db,
)
from app.core.config import settings
from app.db.models.intel.geography import Country
from app.db.models.intel.reports import DailyReport
from app.db.models.intel.user import User
from app.schemas.report import ReportDetail, ReportGenerateRequest, ReportResponse
from app.services.intel.audit import audit_service
from app.services.intel.signing import (
    SigningUnavailableError,
    report_signer,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Inline schemas (kept here because they are signing-specific)
# ---------------------------------------------------------------------------


class ReportSignatureResponse(BaseModel):
    signature: str | None
    canonical_payload_hash: str
    public_key_fingerprint: str | None


# ---------------------------------------------------------------------------
# List / detail / generate (unchanged shapes)
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ReportResponse])
async def list_reports(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ReportResponse]:
    result = await db.execute(
        select(DailyReport)
        .where(DailyReport.published.is_(True))
        .order_by(DailyReport.report_date.desc())
    )
    reports = result.scalars().all()
    return [ReportResponse.model_validate(r) for r in reports]


@router.get("/{report_id}", response_model=ReportDetail)
async def get_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ReportDetail:
    result = await db.execute(
        select(DailyReport).where(
            DailyReport.id == report_id,
            DailyReport.published.is_(True),
        )
    )
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return ReportDetail.model_validate(report)


@router.post("/generate", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def generate_report(
    body: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_institutional_user),
) -> ReportResponse:
    country_result = await db.execute(
        select(Country).where(Country.iso_code == body.country_iso.upper())
    )
    country = country_result.scalars().first()
    if not country:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")

    osint = OSINTAgent()
    signals = await osint.gather_signals(body.country_iso)
    # Synthesis runs at PUBLIC by default — endpoints that surface
    # classified data must pass an explicit higher classification.
    summary = await synthesis_agent.generate_daily_report(country.name, signals)

    report = DailyReport(
        country_id=country.id,
        executive_summary=summary,
        content_json="{}",
        published=False,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return ReportResponse.model_validate(report)


@router.get("/{report_id}/premium", response_model=ReportDetail)
async def get_premium_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_institutional_user),
) -> ReportDetail:
    result = await db.execute(
        select(DailyReport).where(DailyReport.id == report_id)
    )
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return ReportDetail.model_validate(report)


# ---------------------------------------------------------------------------
# Publish — sign-and-mark
# ---------------------------------------------------------------------------


@router.put("/{report_id}/publish", response_model=ReportDetail)
async def publish_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> ReportDetail:
    """Sign the report and mark it as published.

    The sign+publish operation is atomic per HTTP call: if signing
    fails (or is unavailable in state-grade mode), the publish flag
    is never set. The signing audit event is recorded in the same
    transaction.
    """
    result = await db.execute(
        select(DailyReport).where(DailyReport.id == report_id)
    )
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    if report.published:
        # Idempotent re-publish: don't re-sign, just return the row.
        return ReportDetail.model_validate(report)

    # Sign — fail closed in state-grade mode if signing is unavailable.
    if not report_signer.available:
        if settings.STATE_GRADE_MODE:
            await audit_service.record(
                db,
                event_type="report.publish_denied",
                actor_user_id=admin.id,
                resource_type="daily_report",
                resource_id=str(report.id),
                classification=report.classification,
                org_id=report.org_id,
                outcome="error",
                metadata={"reason": "signing_unavailable"},
            )
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Signing required for publication",
            )
        # Non state-grade: refuse anyway. Publishing unsigned reports
        # is never a state we want to ship from this endpoint.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signing service unavailable",
        )

    try:
        signature_blob = report_signer.sign(report)
    except SigningUnavailableError:
        await audit_service.record(
            db,
            event_type="report.publish_denied",
            actor_user_id=admin.id,
            resource_type="daily_report",
            resource_id=str(report.id),
            classification=report.classification,
            org_id=report.org_id,
            outcome="error",
            metadata={"reason": "signing_unavailable"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signing required for publication",
        )

    fingerprint = report_signer.fingerprint
    report.signature = signature_blob
    report.signed_at = datetime.now(timezone.utc)
    report.signature_fingerprint = fingerprint
    report.published = True

    await audit_service.record(
        db,
        event_type="report.signed",
        actor_user_id=admin.id,
        resource_type="daily_report",
        resource_id=str(report.id),
        classification=report.classification,
        org_id=report.org_id,
        outcome="success",
        metadata={
            "fingerprint": fingerprint,
            "classification": int(report.classification or 0),
        },
    )
    await db.commit()
    await db.refresh(report)
    return ReportDetail.model_validate(report)


# ---------------------------------------------------------------------------
# Signature retrieval — clearance-gated
# ---------------------------------------------------------------------------


@router.get(
    "/{report_id}/signature",
    response_model=ReportSignatureResponse,
)
async def get_report_signature(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ReportSignatureResponse:
    """Return the detached signature blob and a canonical hash.

    The endpoint is reachable only through the classified router so
    the MFA + clearance gates already apply. A caller that can read
    the report body itself is automatically allowed to ask for its
    signature.
    """
    result = await db.execute(
        select(DailyReport).where(DailyReport.id == report_id)
    )
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    return ReportSignatureResponse(
        signature=report.signature,
        canonical_payload_hash=report_signer.canonical_payload_hash(report),
        public_key_fingerprint=report.signature_fingerprint,
    )
