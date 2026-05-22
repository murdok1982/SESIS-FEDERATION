from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.osint.deps import *
from app.core.stix import STIXBundle, STIXObject, STIXType
from app.db.models.osint.intel_records import IntelligenceFusionRecord, STIXObjectRecord

router = APIRouter()

class OSINTLookupRequest(BaseModel):
    target: str = Field(..., json_schema_extra={"example": "example.com"})
    modules: list[str] = Field(..., json_schema_extra={"example": ["dns", "whois", "ssl"]})

class STIXResponseSchema(BaseModel):
    id: str = Field(..., json_schema_extra={"example": "bundle--c5264877-ab8c-4f1d-b541-2b04f5e71440"})
    type: str = Field("bundle", json_schema_extra={"example": "bundle"})
    spec_version: str = Field("2.1", json_schema_extra={"example": "2.1"})
    objects: list[dict[str, Any]] = Field(..., json_schema_extra={"example": [{
        "type": "indicator",
        "spec_version": "2.1",
        "id": "indicator--8e2e2d2b-17d4-4cbf-938f-98ee46b3cd3f",
        "created": "2023-01-01T00:00:00.000Z",
        "modified": "2023-01-01T00:00:00.000Z",
        "pattern": "[domain-name:value = 'example.com']",
        "pattern_type": "stix",
        "valid_from": "2023-01-01T00:00:00.000Z"
    }]})

_CLASSIFICATION_ORDER = ["UNCLASSIFIED", "CUI", "CONFIDENTIAL", "SECRET", "TOP_SECRET"]

def _allowed_classifications(user_level: str) -> list[str]:
    try:
        idx = _CLASSIFICATION_ORDER.index(user_level)
    except ValueError:
        idx = 0
    return _CLASSIFICATION_ORDER[: idx + 1]

@router.get("/fusion")
async def list_fusion_records(
    db: DBSession,
    user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Returns fusion records visible to the caller's clearance level."""
    allowed = _allowed_classifications(getattr(user, "classification", "UNCLASSIFIED"))
    q = (
        select(IntelligenceFusionRecord)
        .where(IntelligenceFusionRecord.classification.in_(allowed))
        .order_by(IntelligenceFusionRecord.timestamp.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "fusion_id": r.fusion_id,
            "target": r.target,
            "timestamp": r.timestamp,
            "input_sources": r.input_sources,
            "correlated_entities": r.correlated_entities,
            "relationships_found": r.relationships_found,
            "threat_assessment": r.threat_assessment,
            "confidence": r.confidence,
            "recommendations": r.recommendations,
            "classification": r.classification,
        }
        for r in rows
    ]

@router.get("/stix/export", response_model=STIXResponseSchema)
async def export_stix_bundle(
    db: DBSession,
    user: CurrentUser,
    stix_type: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    """Export a STIX 2.1 Bundle from stored objects visible to the caller.

    Excludes objects whose ``labels`` contain a classification level above the
    caller's clearance (looking for tokens like ``classification:SECRET``).
    """
    allowed = set(_allowed_classifications(getattr(user, "classification", "UNCLASSIFIED")))
    q = select(STIXObjectRecord).limit(limit)
    if stix_type:
        q = q.where(STIXObjectRecord.stix_type == stix_type)
    rows = (await db.execute(q)).scalars().all()

    def _label_classification(labels: list[str] | None) -> str:
        for lbl in labels or []:
            if isinstance(lbl, str) and lbl.upper().startswith("CLASSIFICATION:"):
                return lbl.split(":", 1)[1].strip().upper()
        return "UNCLASSIFIED"

    bundle = STIXBundle()
    for r in rows:
        if _label_classification(r.labels) not in allowed:
            continue
        try:
            stype = STIXType(r.stix_type)
        except ValueError:
            continue
        obj = STIXObject(
            type=stype,
            name=r.name,
            description=r.description or "",
            labels=r.labels or [],
            confidence=r.confidence or 0.0,
            id=r.stix_id,
            created=r.created.isoformat() if r.created else "",
            modified=r.modified.isoformat() if r.modified else "",
            properties=r.properties or {},
            kill_chain_phases=r.kill_chain_phases or [],
            external_references=r.external_references or [],
        )
        bundle.add_object(obj)

    return {
        "id": bundle.id,
        "type": "bundle",
        "spec_version": "2.1",
        "objects": [o.to_stix_dict() for o in bundle.objects],
    }

@router.post("/osint/lookup")
async def osint_lookup(
    request: OSINTLookupRequest,
    user: CurrentUser,
) -> dict:
    """MVP OSINT lookup endpoint."""
    return {
        "target": request.target,
        "status": "processing",
        "modules_invoked": request.modules,
        "message": "OSINT lookup initiated successfully"
    }
