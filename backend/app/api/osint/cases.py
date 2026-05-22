from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.osint.deps import *
    CurrentUser,
    DBSession,
    assert_resource_access,
    require_scope,
    user_can_access_classification,
)
from app.db.models.osint.case import Case, CasePriority, CaseStatus
from app.db.models.osint.entity import Entity
from app.db.models.osint.evidence import Evidence
from app.db.models.osint.job import Job
from app.db.models.osint.case import CaseCreate, CaseListItem, CaseResponse, CaseStatusUpdate, CaseUpdate

router = APIRouter()

@router.get("", response_model=list[CaseListItem])
async def list_cases(
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:cases"))],
    status_filter: str | None = Query(None, alias="status"),
    priority_filter: str | None = Query(None, alias="priority"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[CaseListItem]:
    entity_count_sq = (
        select(Entity.case_id, func.count(Entity.id).label("cnt"))
        .group_by(Entity.case_id)
        .subquery()
    )
    evidence_count_sq = (
        select(Evidence.case_id, func.count(Evidence.id).label("cnt"))
        .group_by(Evidence.case_id)
        .subquery()
    )
    job_count_sq = (
        select(Job.case_id, func.count(Job.id).label("cnt"))
        .group_by(Job.case_id)
        .subquery()
    )

    q = (
        select(
            Case,
            func.coalesce(entity_count_sq.c.cnt, 0).label("entity_count"),
            func.coalesce(evidence_count_sq.c.cnt, 0).label("evidence_count"),
            func.coalesce(job_count_sq.c.cnt, 0).label("job_count"),
        )
        .outerjoin(entity_count_sq, entity_count_sq.c.case_id == Case.id)
        .outerjoin(evidence_count_sq, evidence_count_sq.c.case_id == Case.id)
        .outerjoin(job_count_sq, job_count_sq.c.case_id == Case.id)
        .where(Case.deleted.is_(False))
    )
    is_admin = getattr(user, "is_superuser", False) or "admin" in (
        getattr(user, "scopes", []) or []
    )
    if not is_admin:
        q = q.where(Case.operator_id == user.id)  # type: ignore[attr-defined]
    if status_filter:
        q = q.where(Case.status == status_filter)
    if priority_filter:
        q = q.where(Case.priority == priority_filter)
    q = q.order_by(Case.updated_at.desc()).offset(skip).limit(limit)

    rows = (await db.execute(q)).all()
    items = []
    for row in rows:
        case_obj = row.Case
        if not user_can_access_classification(user, getattr(case_obj, "classification", None)):  # type: ignore[arg-type]
            continue
        item = CaseListItem.model_validate(case_obj)
        item.entity_count = row.entity_count
        item.evidence_count = row.evidence_count
        item.job_count = row.job_count
        items.append(item)
    return items

@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    body: CaseCreate,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("write:cases"))],
) -> CaseResponse:
    case = Case(**body.model_dump(), operator_id=user.id)  # type: ignore[attr-defined]
    db.add(case)
    await db.commit()
    await db.refresh(case)
    response = CaseResponse.model_validate(case)
    return response

@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:cases"))],
) -> CaseResponse:
    case = await _get_or_404(db, case_id, user)  # type: ignore[arg-type]
    ec = await db.scalar(select(func.count(Entity.id)).where(Entity.case_id == case_id)) or 0
    evc = await db.scalar(select(func.count(Evidence.id)).where(Evidence.case_id == case_id)) or 0
    jc = await db.scalar(select(func.count(Job.id)).where(Job.case_id == case_id)) or 0
    response = CaseResponse.model_validate(case)
    response.entity_count = ec
    response.evidence_count = evc
    response.job_count = jc
    return response

@router.put("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: str,
    body: CaseUpdate,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("write:cases"))],
) -> CaseResponse:
    case = await _get_or_404(db, case_id, user)  # type: ignore[arg-type]
    update_data = body.model_dump(exclude_none=True)
    # Mass-assignment guard: only admins can change ownership/classification.
    is_admin = getattr(user, "is_superuser", False) or "admin" in (
        getattr(user, "scopes", []) or []
    )
    if not is_admin:
        for protected in ("operator_id", "classification", "deleted"):
            update_data.pop(protected, None)
    for field, value in update_data.items():
        setattr(case, field, value)
    await db.commit()
    await db.refresh(case)
    return CaseResponse.model_validate(case)

@router.patch("/{case_id}/status", response_model=CaseResponse)
async def update_case_status(
    case_id: str,
    body: CaseStatusUpdate,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("write:cases"))],
) -> CaseResponse:
    case = await _get_or_404(db, case_id, user)  # type: ignore[arg-type]
    case.status = body.status
    await db.commit()
    await db.refresh(case)
    return CaseResponse.model_validate(case)

@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(
    case_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("admin"))],
) -> None:
    case = await _get_or_404(db, case_id, user)  # type: ignore[arg-type]
    case.deleted = True
    await db.commit()

async def _get_or_404(db: AsyncSession, case_id: str, user) -> Case:
    result = await db.execute(select(Case).where(Case.id == case_id, Case.deleted.is_(False)))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    assert_resource_access(
        user,
        owner_id=case.operator_id,
        classification=getattr(case, "classification", "UNCLASSIFIED"),
    )
    return case
