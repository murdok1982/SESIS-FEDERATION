from __future__ import annotations

import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.osint.deps import *
from app.core.config import settings
from app.db.models.osint.case import Case
from app.db.models.osint.evidence import Evidence
from app.db.models.osint.evidence import EvidenceCreate, EvidenceListItem, EvidenceResponse

async def _assert_case_access(db: AsyncSession, case_id: str, user) -> Case:
    """Fetch the parent case and enforce ownership + clearance via shared helper."""
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

router = APIRouter()

# Allow only safe characters in stored filenames; collapse the rest to '_'
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_LEN = 128

def _safe_filename(name: str | None) -> str:
    """Strip directory components and unsafe characters to prevent path traversal.

    Returns a sanitized basename safe to concatenate with a storage directory.
    Never returns an empty string (falls back to ``upload.bin``).
    """
    if not name:
        return "upload.bin"
    # Drop any path components (handles both POSIX and Windows separators)
    base = os.path.basename(name.replace("\\", "/"))
    # Reject NUL bytes / control chars and traversal sequences explicitly
    base = base.replace("\x00", "").lstrip(".")
    base = _SAFE_FILENAME_RE.sub("_", base)
    if not base or base in {".", ".."}:
        return "upload.bin"
    return base[:_MAX_FILENAME_LEN]

_CASE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

def _validate_case_id(case_id: str) -> str:
    if not _CASE_ID_RE.match(case_id or ""):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid case_id",
        )
    return case_id

@router.get("", response_model=list[EvidenceListItem])
async def list_evidence(
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:cases"))],
    case_id: str | None = None,
    entity_id: str | None = None,
    evidence_type: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[EvidenceListItem]:
    if case_id:
        await _assert_case_access(db, case_id, user)

    q = select(Evidence).join(Case, Case.id == Evidence.case_id).where(Case.deleted.is_(False))
    is_admin = getattr(user, "is_superuser", False) or "admin" in (
        getattr(user, "scopes", []) or []
    )
    if not is_admin:
        q = q.where(Case.operator_id == user.id)  # type: ignore[attr-defined]
    if case_id:
        q = q.where(Evidence.case_id == case_id)
    if entity_id:
        q = q.where(Evidence.entity_id == entity_id)
    if evidence_type:
        q = q.where(Evidence.evidence_type == evidence_type)
    q = q.order_by(Evidence.collected_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return [EvidenceListItem.model_validate(e) for e in result.scalars().all()]

@router.post("", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
async def create_evidence(
    body: EvidenceCreate,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("write:cases"))],
) -> EvidenceResponse:
    await _assert_case_access(db, body.case_id, user)

    content_hash = ""
    if body.content_text:
        content_hash = hashlib.sha256(body.content_text.encode()).hexdigest()

    evidence = Evidence(
        **body.model_dump(),
        content_hash=content_hash,
        collected_at=datetime.now(timezone.utc),
        collected_by=str(user.id),  # type: ignore[attr-defined]
    )
    db.add(evidence)
    await db.commit()
    await db.refresh(evidence)
    return EvidenceResponse.model_validate(evidence)

@router.post("/upload", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    case_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("write:cases"))],
    file: UploadFile = File(...),
) -> EvidenceResponse:
    safe_case_id = _validate_case_id(case_id)
    await _assert_case_access(db, safe_case_id, user)

    if file.size and file.size > settings.max_file_size_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

    content = await file.read()
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

    content_hash = hashlib.sha256(content).hexdigest()
    ev_id = str(uuid.uuid4())
    safe_name = _safe_filename(file.filename)

    storage_root = os.path.realpath(settings.EVIDENCE_STORAGE_PATH)
    case_dir = os.path.realpath(os.path.join(storage_root, safe_case_id))
    # Defense-in-depth: ensure the resolved case_dir is still inside storage_root
    if os.path.commonpath([storage_root, case_dir]) != storage_root:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path")
    os.makedirs(case_dir, exist_ok=True)

    file_path = os.path.realpath(os.path.join(case_dir, f"{ev_id}_{safe_name}"))
    if os.path.commonpath([case_dir, file_path]) != case_dir:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path")

    with open(file_path, "wb") as f:
        f.write(content)

    evidence = Evidence(
        id=ev_id,
        case_id=safe_case_id,
        title=safe_name,
        evidence_type="FILE",
        content_hash=content_hash,
        content_file_path=file_path,
        file_size_bytes=len(content),
        collected_at=datetime.now(timezone.utc),
        collected_by=str(user.id),  # type: ignore[attr-defined]
    )
    db.add(evidence)
    await db.commit()
    await db.refresh(evidence)
    return EvidenceResponse.model_validate(evidence)

@router.get("/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(
    evidence_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:cases"))],
) -> EvidenceResponse:
    ev = await _get_or_404(db, evidence_id, user)
    return EvidenceResponse.model_validate(ev)

@router.get("/{evidence_id}/custody")
async def get_evidence_custody(
    evidence_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:cases"))],
) -> dict[str, object]:
    """Returns the chain-of-custody for the evidence, recomputing the SHA-256
    hash of the stored file (if present) to verify integrity on-the-fly.
    """
    from app.db.models.osint.intel_records import ChainOfCustodyRecord
    from sqlalchemy import select as _select

    ev = await _get_or_404(db, evidence_id, user)

    integrity_ok = True
    recomputed_hash = ev.content_hash
    if ev.content_file_path and os.path.exists(ev.content_file_path):
        h = hashlib.sha256()
        with open(ev.content_file_path, "rb") as fp:
            for chunk in iter(lambda: fp.read(1024 * 1024), b""):
                h.update(chunk)
        recomputed_hash = h.hexdigest()
        integrity_ok = (recomputed_hash == ev.content_hash)

    rec = (
        await db.execute(
            _select(ChainOfCustodyRecord).where(ChainOfCustodyRecord.evidence_id == evidence_id)
        )
    ).scalar_one_or_none()

    return {
        "evidence_id": evidence_id,
        "stored_hash": ev.content_hash,
        "recomputed_hash": recomputed_hash,
        "integrity_verified": integrity_ok,
        "collected_at": ev.collected_at.isoformat() if ev.collected_at else None,
        "collected_by": ev.collected_by,
        "custody_chain": (rec.custody_chain if rec else []) or [],
        "last_verification": (
            rec.last_verification.isoformat() if rec and rec.last_verification else None
        ),
    }

@router.get("/{evidence_id}/content")
async def get_evidence_content(
    evidence_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:cases"))],
) -> FileResponse:
    ev = await _get_or_404(db, evidence_id, user)
    if not ev.content_file_path or not os.path.exists(ev.content_file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    # Confine reads to the configured evidence storage root
    storage_root = os.path.realpath(settings.EVIDENCE_STORAGE_PATH)
    real_path = os.path.realpath(ev.content_file_path)
    if os.path.commonpath([storage_root, real_path]) != storage_root:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Path outside storage root")
    return FileResponse(real_path)

@router.delete("/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evidence(
    evidence_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("admin"))],
) -> None:
    ev = await _get_or_404(db, evidence_id, user)
    if ev.content_file_path and os.path.exists(ev.content_file_path):
        os.remove(ev.content_file_path)
    await db.delete(ev)
    await db.commit()

async def _get_or_404(db: AsyncSession, evidence_id: str, user) -> Evidence:
    result = await db.execute(select(Evidence).where(Evidence.id == evidence_id))
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    await _assert_case_access(db, ev.case_id, user)
    return ev
