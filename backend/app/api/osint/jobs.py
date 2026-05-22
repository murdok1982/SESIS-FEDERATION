from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.osint.deps import *
from app.db.models.osint.case import Case
from app.db.models.osint.job import Job, JobStatus
from app.db.models.osint.job import JobCreate, JobListItem, JobResponse

router = APIRouter()

async def _assert_case_access(db: AsyncSession, case_id: str, user) -> Case:
    case = (
        await db.execute(select(Case).where(Case.id == case_id, Case.deleted.is_(False)))
    ).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    assert_resource_access(
        user,
        owner_id=case.operator_id,
        classification=getattr(case, "classification", "UNCLASSIFIED"),
    )
    return case

@router.get("", response_model=list[JobListItem])
async def list_jobs(
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:cases"))],
    case_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[JobListItem]:
    if case_id:
        await _assert_case_access(db, case_id, user)

    q = select(Job).outerjoin(Case, Case.id == Job.case_id)
    is_admin = getattr(user, "is_superuser", False) or "admin" in (
        getattr(user, "scopes", []) or []
    )
    if not is_admin:
        # Either job's case belongs to user OR job has no case and user created it.
        q = q.where(
            (Case.operator_id == user.id)  # type: ignore[attr-defined]
            | ((Job.case_id.is_(None)) & (Job.created_by == user.id))  # type: ignore[attr-defined]
        )
    if case_id:
        q = q.where(Job.case_id == case_id)
    if status_filter:
        q = q.where(Job.status == status_filter)
    q = q.order_by(Job.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return [JobListItem.model_validate(j) for j in result.scalars().all()]

@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobCreate,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("execute:jobs"))],
) -> JobResponse:
    if body.case_id:
        await _assert_case_access(db, body.case_id, user)

    job = Job(
        id=str(uuid.uuid4()),
        case_id=body.case_id,
        job_type=body.job_type,
        status=JobStatus.PENDING,
        created_by=user.id,  # type: ignore[attr-defined]
        task_description=body.task_description,
        input_params={**body.input_params, **({"task": body.task_description} if body.task_description else {})},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue via ARQ
    try:
        from app.jobs.tasks import enqueue_job  # noqa: PLC0415
        arq_id = await enqueue_job(job)
        job.arq_job_id = arq_id
        job.status = JobStatus.QUEUED
        await db.commit()
        await db.refresh(job)
    except Exception:
        pass

    return JobResponse.model_validate(job)

@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:cases"))],
) -> JobResponse:
    job = await _get_or_404(db, job_id, user)
    return JobResponse.model_validate(job)

@router.post("/{job_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("execute:jobs"))],
) -> None:
    job = await _get_or_404(db, job_id, user)
    if job.status not in (JobStatus.PENDING, JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job cannot be cancelled")
    job.status = JobStatus.CANCELLED
    await db.commit()

async def _get_or_404(db: AsyncSession, job_id: str, user) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.case_id:
        await _assert_case_access(db, job.case_id, user)
    else:
        assert_resource_access(user, owner_id=job.created_by, classification="UNCLASSIFIED")
    return job
