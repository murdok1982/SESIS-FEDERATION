from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import os

from app.api.osint.deps import *
from app.core.config import settings
from app.db.models.osint.case import Case
from app.db.models.osint.report import Report
from app.db.models.osint.report import ReportGenerateRequest, ReportListItem, ReportResponse

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

@router.get("", response_model=list[ReportListItem])
async def list_reports(
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:reports"))],
    case_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[ReportListItem]:
    if case_id:
        await _assert_case_access(db, case_id, user)

    q = select(Report).join(Case, Case.id == Report.case_id).where(Case.deleted.is_(False))
    is_admin = getattr(user, "is_superuser", False) or "admin" in (
        getattr(user, "scopes", []) or []
    )
    if not is_admin:
        q = q.where(Case.operator_id == user.id)  # type: ignore[attr-defined]
    if case_id:
        q = q.where(Report.case_id == case_id)
    q = q.order_by(Report.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return [ReportListItem.model_validate(r) for r in result.scalars().all()]

@router.post("/generate", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def generate_report(
    body: ReportGenerateRequest,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("write:reports"))],
) -> dict:
    from app.db.models.osint.job import Job, JobStatus, JobType  # noqa: PLC0415
    import uuid  # noqa: PLC0415

    await _assert_case_access(db, body.case_id, user)

    job = Job(
        id=str(uuid.uuid4()),
        case_id=body.case_id,
        job_type=JobType.REPORT_GENERATION,
        status=JobStatus.PENDING,
        created_by=str(user.id),  # type: ignore[attr-defined]
        input_params={
            "report_type": body.report_type,
            "entity_ids": body.entity_ids,
            "format": body.format,
        },
    )
    db.add(job)
    await db.commit()
    return {"job_id": job.id, "message": "Report generation queued"}

@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:reports"))],
) -> ReportResponse:
    report = await _get_or_404(db, report_id, user)
    return ReportResponse.model_validate(report)

@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:reports"))],
) -> FileResponse:
    report = await _get_or_404(db, report_id, user)
    if not report.file_path or not os.path.exists(report.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found")
    storage_root = os.path.realpath(settings.REPORTS_STORAGE_PATH)
    real_path = os.path.realpath(report.file_path)
    if os.path.commonpath([storage_root, real_path]) != storage_root:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Path outside storage root")
    return FileResponse(real_path)

@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("write:reports"))],
) -> None:
    report = await _get_or_404(db, report_id, user)
    if report.file_path and os.path.exists(report.file_path):
        storage_root = os.path.realpath(settings.REPORTS_STORAGE_PATH)
        real_path = os.path.realpath(report.file_path)
        if os.path.commonpath([storage_root, real_path]) == storage_root:
            os.remove(real_path)
    await db.delete(report)
    await db.commit()

async def _get_or_404(db: AsyncSession, report_id: str, user) -> Report:
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    if report.case_id:
        await _assert_case_access(db, report.case_id, user)
    return report
