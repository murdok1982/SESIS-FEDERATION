from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import select, desc

from app.api.osint.deps import *
from app.core.audit import audit_chain
from app.db.models.osint.audit_log import AuditLog
from app.db.models.osint.intel_records import AuditChainEntry

router = APIRouter()

@router.get("")
async def list_audit_log(
    db: DBSession,
    _admin: AdminUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    action: str | None = None,
    user_id: str | None = None,
    success: bool | None = None,
) -> list[dict[str, Any]]:
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if success is not None:
        q = q.where(AuditLog.success == success)
    q = q.order_by(desc(AuditLog.timestamp)).offset(skip).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "username": r.username,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "ip_address": r.ip_address,
            "user_agent": r.user_agent,
            "request_id": r.request_id,
            "success": r.success,
            "error_message": r.error_message,
            "details": r.details,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rows
    ]

@router.get("/chain")
async def list_audit_chain(
    db: DBSession,
    _admin: AdminUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[dict[str, Any]]:
    q = (
        select(AuditChainEntry)
        .order_by(AuditChainEntry.index.asc())
        .offset(skip)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "index": r.index,
            "timestamp": r.timestamp,
            "action": r.action,
            "user_id": r.user_id,
            "resource": r.resource,
            "details": r.details,
            "previous_hash": r.previous_hash,
            "hash": r.hash_value,
        }
        for r in rows
    ]

@router.get("/verify")
async def verify_chain_endpoint(
    db: DBSession,
    _admin: AdminUser,
) -> dict[str, Any]:
    """Walks the audit_chain and recomputes every hash. Detects tampering.

    Returns ``{ok, total, broken_at, last_hash, reason?}``.
    """
    return await verify_audit_chain(db)
