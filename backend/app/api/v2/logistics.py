"""
Logistics API v2.
Cadena de suministro, munición, personal, MEDEVAC.
"""
from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Optional, List
from datetime import datetime
import uuid

from pydantic import BaseModel, Field

from app.db.session import async_session_factory
from app.models.persistence import LogisticsSupply, EventStore, ORBATUnit
from app.core.config import settings

router = APIRouter()


async def get_db():
    async with async_session_factory() as session:
        yield session


class SupplyIn(BaseModel):
    item_type: str = Field(..., max_length=64, pattern=r"^[A-Z0-9_]+$")
    quantity: float = Field(..., ge=0.0)
    unit: str = Field(..., max_length=32, pattern=r"^[A-Za-z_]+$")
    location_id: Optional[str] = Field(None, max_length=64)
    min_threshold: Optional[float] = Field(None, ge=0.0)
    classification: str = Field("CONFIDENTIAL", max_length=32, pattern=r"^(OPEN|RESTRICTED|CONFIDENTIAL|SECRET|TOP_SECRET)$")


class ConsumeIn(BaseModel):
    quantity: float = Field(..., gt=0.0)


class MedevacPriority(str, Enum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class MedevacIn(BaseModel):
    unit_id: str = Field(..., max_length=64)
    priority: MedevacPriority
    casualties: int = Field(..., ge=1, le=1000)
    location_desc: Optional[str] = Field(None, max_length=200)


@router.post("/supplies", tags=["Logistics / Supplies"])
async def add_supply(
    payload: SupplyIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("CONFIDENTIAL")),
):
    """Agrega suministros al inventario."""
    supply = LogisticsSupply(
        id=str(uuid.uuid4()),
        item_type=payload.item_type,
        quantity=payload.quantity,
        unit=payload.unit,
        location_id=payload.location_id,
        min_threshold=payload.min_threshold,
        classification_level=payload.classification,
        last_updated=datetime.utcnow()
    )
    db.add(supply)

    event = EventStore(
        aggregate_id=supply.id,
        aggregate_type="LogisticsSupply",
        event_type="SUPPLY_ADDED",
        payload={"type": payload.item_type, "qty": payload.quantity, "unit": payload.unit}
    )
    db.add(event)

    await db.commit()
    return {"id": supply.id, "status": "added"}


@router.get("/supplies", tags=["Logistics / Supplies"])
async def list_supplies(
    item_type: Optional[str] = None,
    location_id: Optional[str] = None,
    low_stock: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("CONFIDENTIAL")),
):
    """Lista suministros. low_stock=true muestra solo por debajo del umbral."""
    query = select(LogisticsSupply)
    if item_type:
        query = query.where(LogisticsSupply.item_type == item_type)
    if location_id:
        query = query.where(LogisticsSupply.location_id == location_id)

    result = await db.execute(query)
    supplies = result.scalars().all()

    items = []
    for s in supplies:
        is_low = s.min_threshold and s.quantity <= s.min_threshold
        if low_stock and not is_low:
            continue
        items.append({
            "id": s.id,
            "type": s.item_type,
            "quantity": s.quantity,
            "unit": s.unit,
            "location_id": s.location_id,
            "min_threshold": s.min_threshold,
            "is_low_stock": is_low,
            "last_updated": s.last_updated
        })

    return {"supplies": items, "total": len(items)}


@router.put("/supplies/{supply_id}/consume", tags=["Logistics / Supplies"])
async def consume_supply(
    supply_id: str,
    payload: ConsumeIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("CONFIDENTIAL")),
):
    """Consume suministros (ej: munición disparada)."""
    result = await db.execute(select(LogisticsSupply).where(LogisticsSupply.id == supply_id))
    supply = result.scalar_one_or_none()

    if not supply:
        raise HTTPException(status_code=404, detail="Suministro no encontrado")

    if supply.quantity < payload.quantity:
        raise HTTPException(status_code=400, detail="Cantidad insuficiente")

    supply.quantity -= payload.quantity
    supply.last_updated = datetime.utcnow()

    event = EventStore(
        aggregate_id=supply_id,
        aggregate_type="LogisticsSupply",
        event_type="SUPPLY_CONSUMED",
        payload={"qty_consumed": payload.quantity, "remaining": supply.quantity}
    )
    db.add(event)

    await db.commit()
    return {
        "supply_id": supply_id,
        "remaining": supply.quantity,
        "is_low_stock": supply.min_threshold and supply.quantity <= supply.min_threshold
    }


@router.get("/personnel", tags=["Logistics / Personnel"])
async def get_personnel_status(
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("CONFIDENTIAL")),
):
    """Obtiene estado de personal por unidad (OPDIS)."""
    result = await db.execute(select(ORBATUnit).where(ORBATUnit.unit_type.in_(["tierra", "mar", "aire"])))
    units = result.scalars().all()

    # TODO: Conectar con módulo de RRHH real
    personnel = []
    for u in units:
        personnel.append({
            "unit_id": u.id,
            "unit_name": u.name,
            "type": u.unit_type,
            "status": u.status,
            "assigned": "N/A",  # TODO: tabla personnel
            "ready": "N/A",
            "medical": "N/A"
        })

    return {"personnel": personnel, "total_units": len(personnel)}


@router.post("/medevac", tags=["Logistics / Medical"])
async def request_medevac(
    payload: MedevacIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("CONFIDENTIAL")),
):
    """Solicita evacuación médica (MEDEVAC)."""
    medevac_id = str(uuid.uuid4())

    event = EventStore(
        aggregate_id=medevac_id,
        aggregate_type="Medevac",
        event_type="MEDEVAC_REQUESTED",
        payload={
            "unit_id": payload.unit_id,
            "priority": payload.priority.value,
            "casualties": payload.casualties,
            "location": payload.location_desc
        },
        actor="medical_officer"
    )
    db.add(event)

    await db.commit()
    return {
        "medevac_id": medevac_id,
        "priority": payload.priority.value,
        "status": "requested",
        "estimated_arrival": "15-45 minutes" if payload.priority == MedevacPriority.T1 else "1-3 hours"
    }
