"""
Intelligence Fusion API — multi-INT product generation and PIR management.

Endpoints for fusing intelligence from multiple sources and managing
Priority Intelligence Requirements (PIRs).
"""
import datetime
import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger("sesis.api.intel")

router = APIRouter()

# ---------------------------------------------------------------------------
# ABAC (reuses pattern from brain.py)
# ---------------------------------------------------------------------------

CLEARANCE_ORDER = {
    "OPEN": 0,
    "RESTRICTED": 1,
    "CONFIDENTIAL": 2,
    "SECRET": 3,
    "TOP_SECRET": 4,
}


async def require_restricted_clearance(request: Request) -> dict[str, Any]:
    """RESTRICTED+ required for intel endpoints."""
    api_key = (
        request.headers.get("X-API-Key")
        or request.headers.get("Authorization", "").removeprefix("Bearer ")
    )
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    operator_keys = settings.get_operator_api_keys()
    operator = operator_keys.get(api_key)
    if not operator:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    clearance = operator.get("clearance", "OPEN")
    if CLEARANCE_ORDER.get(clearance, 0) < CLEARANCE_ORDER["RESTRICTED"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"RESTRICTED clearance required. Your clearance: {clearance}",
        )
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
# Schemas
# ---------------------------------------------------------------------------

ProductType = Literal["INTSUM", "SITREP", "THREATSUM", "COA_BRIEF", "STRAT_BRIEF"]


class IntelFuseRequest(BaseModel):
    events: list[dict[str, Any]] = Field(..., min_length=1, description="Raw intel events")


class IntelProductRequest(BaseModel):
    product_type: ProductType
    data: dict[str, Any] = Field(..., description="Source data for product generation")
    classification: str = "CONFIDENTIAL"
    requestor: str = "SYSTEM"


class PIRCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10)
    priority: int = Field(..., ge=1, le=5, description="1=highest, 5=lowest")
    collection_methods: list[str] = Field(default_factory=list)
    due_date: datetime.datetime | None = None
    classification: str = "CONFIDENTIAL"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/fuse", summary="Fuse multiple intelligence reports")
async def fuse_intel(
    payload: IntelFuseRequest,
    request: Request,
    operator: dict = Depends(require_restricted_clearance),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Accept raw intelligence events from any INT source and return a
    fused assessment. Automatically invokes ARES LLM when fusion score
    exceeds 0.70.
    """
    service = IntelFusionService(db)
    fusion = await service.fuse_events(payload.events)

    await _log_audit(
        db,
        actor=operator.get("name", "UNKNOWN"),
        action="INTEL_FUSE",
        resource_type="INTEL_FUSION",
        resource_id=fusion.fusion_id,
        context={
            "source_count": len(payload.events),
            "fusion_score": fusion.fusion_score,
        },
    )

    return fusion.to_dict()


@router.get("/products", summary="List generated intelligence products")
async def list_products(
    product_type: str | None = Query(None),
    classification: str | None = Query(None),
    limit: int = Query(default=20, ge=1, le=100),
    operator: dict = Depends(require_restricted_clearance),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List intelligence products, optionally filtered by type and classification."""
    stmt = select(IntelligenceProduct).order_by(desc(IntelligenceProduct.created_at)).limit(limit)
    if product_type:
        stmt = stmt.where(IntelligenceProduct.product_type == product_type.upper())
    if classification:
        stmt = stmt.where(IntelligenceProduct.classification_level == classification.upper())

    # Enforce clearance: operators only see products at or below their level
    operator_level = CLEARANCE_ORDER.get(operator.get("clearance", "OPEN"), 0)
    rows = (await db.execute(stmt)).scalars().all()

    products = []
    for row in rows:
        row_level = CLEARANCE_ORDER.get(row.classification_level, 0)
        if row_level <= operator_level:
            products.append(
                {
                    "id": row.id,
                    "product_type": row.product_type,
                    "classification": row.classification_level,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "created_by": row.created_by,
                    "content_preview": (row.content or "")[:300],
                }
            )

    return products


@router.get("/products/{product_id}", summary="Get intelligence product detail")
async def get_product(
    product_id: str,
    operator: dict = Depends(require_restricted_clearance),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve full content of a specific intelligence product."""
    result = await db.execute(
        select(IntelligenceProduct).where(IntelligenceProduct.id == product_id)
    )
    product = result.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Intelligence product not found")

    product_level = CLEARANCE_ORDER.get(product.classification_level, 0)
    operator_level = CLEARANCE_ORDER.get(operator.get("clearance", "OPEN"), 0)
    if product_level > operator_level:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient clearance to access this intelligence product",
        )

    return {
        "id": product.id,
        "product_type": product.product_type,
        "classification": product.classification_level,
        "content": product.content,
        "source_data": product.source_data,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "created_by": product.created_by,
    }


@router.post("/products", summary="Generate an intelligence product", status_code=201)
async def create_product(
    payload: IntelProductRequest,
    request: Request,
    operator: dict = Depends(require_restricted_clearance),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate and persist a formal intelligence product (INTSUM, SITREP, etc.)."""
    service = IntelFusionService(db)
    data = {**payload.data, "classification": payload.classification, "requestor": operator.get("name", payload.requestor)}
    product = await service.generate_intelligence_product(payload.product_type, data)

    await _log_audit(
        db,
        actor=operator.get("name", "UNKNOWN"),
        action="INTEL_PRODUCT_GENERATE",
        resource_type="INTEL_PRODUCT",
        resource_id=product["id"],
        context={"product_type": payload.product_type},
    )

    return product


@router.post("/pir", summary="Create Priority Intelligence Requirement", status_code=201)
async def create_pir(
    payload: PIRCreate,
    request: Request,
    operator: dict = Depends(require_restricted_clearance),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Register a new Priority Intelligence Requirement (PIR)."""
    pir_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow()

    pir = PriorityIntelligenceRequirement(
        id=pir_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        collection_methods=payload.collection_methods,
        due_date=payload.due_date,
        classification_level=payload.classification,
        created_by=operator.get("name", "UNKNOWN"),
        is_active=True,
        created_at=now,
    )
    db.add(pir)
    await db.commit()

    await _log_audit(
        db,
        actor=operator.get("name", "UNKNOWN"),
        action="PIR_CREATE",
        resource_type="PIR",
        resource_id=pir_id,
        context={"priority": payload.priority},
    )

    return {
        "id": pir_id,
        "title": payload.title,
        "priority": payload.priority,
        "classification": payload.classification,
        "created_at": now.isoformat(),
        "is_active": True,
    }


@router.get("/pir", summary="List active Priority Intelligence Requirements")
async def list_pirs(
    active_only: bool = Query(default=True),
    operator: dict = Depends(require_restricted_clearance),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List Priority Intelligence Requirements ordered by priority."""
    stmt = select(PriorityIntelligenceRequirement).order_by(
        PriorityIntelligenceRequirement.priority
    )
    if active_only:
        stmt = stmt.where(PriorityIntelligenceRequirement.is_active == True)  # noqa: E712

    operator_level = CLEARANCE_ORDER.get(operator.get("clearance", "OPEN"), 0)
    rows = (await db.execute(stmt)).scalars().all()

    pirs = []
    for row in rows:
        row_level = CLEARANCE_ORDER.get(row.classification_level, 0)
        if row_level <= operator_level:
            pirs.append(
                {
                    "id": row.id,
                    "title": row.title,
                    "description": row.description,
                    "priority": row.priority,
                    "collection_methods": row.collection_methods,
                    "due_date": row.due_date.isoformat() if row.due_date else None,
                    "classification": row.classification_level,
                    "created_by": row.created_by,
                    "is_active": row.is_active,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )

    return pirs


@router.delete("/pir/{pir_id}", summary="Deactivate a PIR", status_code=204)
async def deactivate_pir(
    pir_id: str,
    operator: dict = Depends(require_restricted_clearance),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Mark a PIR as inactive (soft delete)."""
    result = await db.execute(
        select(PriorityIntelligenceRequirement).where(
            PriorityIntelligenceRequirement.id == pir_id
        )
    )
    pir = result.scalars().first()
    if not pir:
        raise HTTPException(status_code=404, detail="PIR not found")

    pir.is_active = False
    await db.commit()

    await _log_audit(
        db,
        actor=operator.get("name", "UNKNOWN"),
        action="PIR_DEACTIVATE",
        resource_type="PIR",
        resource_id=pir_id,
        context={},
    )
