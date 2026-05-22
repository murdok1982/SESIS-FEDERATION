"""
ARES Brain API — Military LLM intelligence endpoints.

All endpoints require clearance >= CONFIDENTIAL enforced via ABAC policy.
Rate limited to 20 requests/minute per operator to protect LLM resources.
"""
import datetime
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.config import settings
from app.db.session import get_db
from app.db.models.persistence import Alert, Event, AuditLog
from app.services.military_brain import military_brain
from app.services.policy import PolicyEvaluator

logger = logging.getLogger("sesis.api.brain")

router = APIRouter()

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

CLEARANCE_ORDER = {
    "OPEN": 0,
    "RESTRICTED": 1,
    "CONFIDENTIAL": 2,
    "SECRET": 3,
    "TOP_SECRET": 4,
}


class QueryRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    context: dict[str, Any] | None = None


class ThreatAnalysisRequest(BaseModel):
    threat_data: dict[str, Any] = Field(..., description="Threat entity/event data")
    context: dict[str, Any] = Field(default_factory=dict)


class COARequest(BaseModel):
    situation: dict[str, Any] = Field(..., description="Current operational situation")
    assets: list[dict[str, Any]] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class StrategicBriefingRequest(BaseModel):
    last_n_events: int = Field(default=50, ge=1, le=200)
    last_n_alerts: int = Field(default=20, ge=1, le=100)
    min_severity: str | None = None


class IntelAssessRequest(BaseModel):
    intel_items: list[dict[str, Any]] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# ABAC dependency
# ---------------------------------------------------------------------------

_rate_limit_store: dict[str, list[datetime.datetime]] = {}


def _check_rate_limit(operator_id: str, limit: int = 20, window_seconds: int = 60) -> None:
    """
    Simple in-process sliding-window rate limiter.
    Raises HTTP 429 if the operator exceeds `limit` calls in `window_seconds`.
    In production, replace with Redis-backed counter.
    """
    now = datetime.datetime.utcnow()
    cutoff = now - datetime.timedelta(seconds=window_seconds)
    
    # Limpieza global para evitar memory leak (CWE-400)
    for k in list(_rate_limit_store.keys()):
        _rate_limit_store[k] = [ts for ts in _rate_limit_store[k] if ts > cutoff]
        if not _rate_limit_store[k]:
            del _rate_limit_store[k]

    calls = _rate_limit_store.get(operator_id, [])
    if len(calls) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {limit} requests per {window_seconds}s",
        )
    calls.append(now)
    _rate_limit_store[operator_id] = calls


async def require_confidential_clearance(request: Request) -> dict[str, Any]:
    """
    Dependency that validates operator API key and enforces minimum
    CONFIDENTIAL clearance for brain endpoints.
    """
    api_key = (
        request.headers.get("X-API-Key")
        or request.headers.get("Authorization", "").removeprefix("Bearer ")
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    operator_keys = settings.get_operator_api_keys()
    operator = operator_keys.get(api_key)
    if not operator:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    clearance = operator.get("clearance", "OPEN")
    if CLEARANCE_ORDER.get(clearance, 0) < CLEARANCE_ORDER["CONFIDENTIAL"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Insufficient clearance. CONFIDENTIAL or above required. "
                f"Your clearance: {clearance}"
            ),
        )

    _check_rate_limit(operator.get("name", api_key))
    return operator


async def _log_audit(
    db: AsyncSession,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    context: dict[str, Any],
) -> None:
    try:
        entry = AuditLog(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            context=context,
        )
        db.add(entry)
        await db.commit()
    except Exception as exc:
        logger.error("Audit log write failed: %s", exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", summary="LLM model status")
async def brain_status(
    _operator: dict = Depends(require_confidential_clearance),
) -> dict[str, Any]:
    """Return operational status of the ARES LLM backend."""
    return await military_brain.get_status()


@router.post("/query", summary="Free-form military query")
async def brain_query(
    payload: QueryRequest,
    request: Request,
    operator: dict = Depends(require_confidential_clearance),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Send a free-form prompt to the ARES military AI brain.
    Response is in NATO military doctrine format.
    """
    response = await military_brain.query(payload.prompt, payload.context)

    await _log_audit(
        db,
        actor=operator.get("name", "UNKNOWN"),
        action="BRAIN_QUERY",
        resource_type="LLM",
        resource_id="ares",
        context={"prompt_length": len(payload.prompt)},
    )

    return {
        "response": response,
        "model": settings.OLLAMA_MODEL,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


@router.post("/analyze-threat", summary="Threat analysis with INTSUM and COAs")
async def analyze_threat(
    payload: ThreatAnalysisRequest,
    request: Request,
    operator: dict = Depends(require_confidential_clearance),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Full threat analysis: produces SITREP, INTSUM, COA options, and risk assessment.
    """
    result = await military_brain.analyze_threat(payload.threat_data, payload.context)

    await _log_audit(
        db,
        actor=operator.get("name", "UNKNOWN"),
        action="THREAT_ANALYSIS",
        resource_type="THREAT",
        resource_id=payload.threat_data.get("id", "unknown"),
        context={"threat_type": payload.threat_data.get("type")},
    )

    return {
        "analysis": result,
        "model": settings.OLLAMA_MODEL,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


@router.post("/generate-coa", summary="Generate Courses of Action")
async def generate_coa(
    payload: COARequest,
    request: Request,
    operator: dict = Depends(require_confidential_clearance),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Apply NATO MDMP to generate Courses of Action for a given operational situation.
    """
    result = await military_brain.generate_coa(
        payload.situation, payload.assets, payload.constraints
    )

    await _log_audit(
        db,
        actor=operator.get("name", "UNKNOWN"),
        action="COA_GENERATION",
        resource_type="OPERATION",
        resource_id=payload.situation.get("operation_id", "unknown"),
        context={"asset_count": len(payload.assets)},
    )

    return {
        "coa": result,
        "model": settings.OLLAMA_MODEL,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


@router.post("/strategic-briefing", summary="Auto-generate strategic briefing")
async def strategic_briefing(
    payload: StrategicBriefingRequest,
    request: Request,
    operator: dict = Depends(require_confidential_clearance),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Pull the last N events and alerts from the database and generate
    an automatic strategic briefing via ARES.
    """
    event_stmt = select(Event).order_by(desc(Event.ts)).limit(payload.last_n_events)
    alert_stmt = select(Alert).order_by(desc(Alert.id)).limit(payload.last_n_alerts)
    if payload.min_severity:
        alert_stmt = alert_stmt.where(Alert.severity == payload.min_severity.upper())

    event_rows = (await db.execute(event_stmt)).scalars().all()
    alert_rows = (await db.execute(alert_stmt)).scalars().all()

    events_data = [
        {
            "event_id": r.event_id,
            "event_type": r.event_type,
            "asset_id": r.asset_id,
            "ts": r.ts.isoformat() if r.ts else None,
            "classification_level": r.classification_level,
            "confidence_score": r.confidence_score,
        }
        for r in event_rows
    ]
    alerts_data = [
        {
            "id": r.id,
            "rule_id": r.rule_id,
            "severity": r.severity,
            "description": r.description,
            "is_anomaly": r.is_anomaly,
            "human_validated": r.human_validated,
        }
        for r in alert_rows
    ]

    briefing = await military_brain.generate_strategic_briefing(events_data, alerts_data)

    await _log_audit(
        db,
        actor=operator.get("name", "UNKNOWN"),
        action="STRATEGIC_BRIEFING",
        resource_type="BRIEFING",
        resource_id="auto",
        context={
            "events_included": len(events_data),
            "alerts_included": len(alerts_data),
        },
    )

    return {
        "briefing": briefing,
        "events_analysed": len(events_data),
        "alerts_analysed": len(alerts_data),
        "model": settings.OLLAMA_MODEL,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
