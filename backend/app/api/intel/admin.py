import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.api.intel.deps import get_db, get_current_admin
from app.db.models.intel.audit import AuditEvent
from app.db.models.intel.user import User
from app.db.models.intel.interactions import ContributorSubmission
from app.db.models.intel.geography import Country
from app.db.models.intel.intelligence import IntelligenceItem
from app.db.models.intel.reports import DailyReport
from app.schemas.user import UserResponse
from app.services.intel.audit import audit_service

router = APIRouter()


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    user_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    country_count = (await db.execute(select(func.count(Country.id)))).scalar() or 0
    intel_count = (await db.execute(select(func.count(IntelligenceItem.id)))).scalar() or 0
    report_count = (await db.execute(select(func.count(DailyReport.id)))).scalar() or 0
    pending_contributions = (
        await db.execute(
            select(func.count(ContributorSubmission.id)).where(
                ContributorSubmission.status == "pending_review"
            )
        )
    ).scalar() or 0

    return {
        "users": user_count,
        "countries": country_count,
        "intelligence_items": intel_count,
        "reports": report_count,
        "pending_contributions": pending_contributions,
    }


@router.get("/contributions")
async def list_contributions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[dict]:
    result = await db.execute(
        select(ContributorSubmission).where(
            ContributorSubmission.status == "pending_review"
        ).order_by(ContributorSubmission.created_at.desc())
    )
    contributions = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "alias": c.alias,
            "country": c.country,
            "category": c.category,
            "description": c.description,
            "actors": c.actors,
            "confidence": c.confidence,
            "status": c.status,
            "created_at": c.created_at.isoformat(),
        }
        for c in contributions
    ]


@router.patch("/contributions/{contribution_id}")
async def review_contribution(
    contribution_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    action: str = body.get("action", "")
    if action not in ("approve", "reject"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="action must be 'approve' or 'reject'",
        )

    result = await db.execute(
        select(ContributorSubmission).where(ContributorSubmission.id == contribution_id)
    )
    contribution = result.scalars().first()
    if not contribution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contribution not found")

    contribution.status = "approved" if action == "approve" else "rejected"
    await db.commit()
    return {"id": str(contribution.id), "status": contribution.status}


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[UserResponse]:
    result = await db.execute(
        select(User).offset((page - 1) * size).limit(size)
    )
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


# ---------------------------------------------------------------------------
# Audit log integrity & query
# ---------------------------------------------------------------------------


@router.get("/audit/verify")
async def audit_verify(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    """Recompute the hash chain and report integrity status.

    Admin-only. Exposed under the classified router, so the MFA
    dependency guarantees the caller has a fresh second factor.
    """
    return await audit_service.verify_chain(db)


@router.get("/audit/events")
async def audit_events(
    event_type: Optional[str] = Query(None),
    actor_user_id: Optional[uuid.UUID] = Query(None),
    classification: Optional[int] = Query(None),
    from_ts: Optional[datetime] = Query(None, alias="from"),
    to_ts: Optional[datetime] = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[dict]:
    stmt = select(AuditEvent).order_by(AuditEvent.timestamp.desc())
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if actor_user_id:
        stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
    if classification is not None:
        stmt = stmt.where(AuditEvent.classification == classification)
    if from_ts:
        stmt = stmt.where(AuditEvent.timestamp >= from_ts)
    if to_ts:
        stmt = stmt.where(AuditEvent.timestamp <= to_ts)
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "timestamp": r.timestamp.isoformat(),
            "actor_user_id": str(r.actor_user_id) if r.actor_user_id else None,
            "actor_ip": r.actor_ip,
            "event_type": r.event_type,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "classification": r.classification,
            "org_id": str(r.org_id) if r.org_id else None,
            "outcome": r.outcome,
            "metadata_json": r.metadata_json,
            "row_hash": r.row_hash,
            "prev_hash": r.prev_hash,
        }
        for r in rows
    ]
