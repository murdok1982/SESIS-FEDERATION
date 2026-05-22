"""
C2 API — Command & Control v2.
Gestión de misiones, ORBAT, órdenes, Blue/Red Force Tracking.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Optional, List
from datetime import datetime
import uuid

from app.db.session import async_session_factory
from app.models.persistence import (
    ORBATUnit, Mission, BlueForceTracking, EventStore
)
from app.core.config import settings
from pydantic import BaseModel, Field

router = APIRouter()
jwt_service = JWTService(settings.JWT_SECRET_KEY)


# ── Pydantic schemas v2 ────────────────────────────────────────────

class ORBATUnitIn(BaseModel):
    name: str = Field(..., max_length=200)
    unit_type: str = Field(..., max_length=50, pattern=r"^[A-Za-z_\-]+$")
    parent_id: Optional[str] = Field(None, max_length=64)
    classification: str = Field("CONFIDENTIAL", max_length=32, pattern=r"^(OPEN|RESTRICTED|CONFIDENTIAL|SECRET|TOP_SECRET)$")


class MissionIn(BaseModel):
    name: str = Field(..., max_length=200)
    mission_type: str = Field(..., max_length=64, pattern=r"^[A-Z_]+$")
    orbat_unit_id: str = Field(..., max_length=64)
    classification: str = Field("SECRET", max_length=32, pattern=r"^(OPEN|RESTRICTED|CONFIDENTIAL|SECRET|TOP_SECRET)$")
    description: Optional[str] = Field(None, max_length=2000)


class MissionStatusIn(BaseModel):
    new_status: str = Field(..., max_length=32, pattern=r"^(PLANNED|ACTIVE|COMPLETED|ABORTED)$")


class BlueForceReportIn(BaseModel):
    unit_id: str = Field(..., max_length=64)
    asset_id: Optional[str] = Field(None, max_length=64)
    lat: float
    lon: float
    altitude: Optional[float] = None
    heading: Optional[float] = None
    speed: Optional[float] = None


class OrderIn(BaseModel):
    mission_id: str = Field(..., max_length=64)
    content: str = Field(..., max_length=8000)
    classification: str = Field("SECRET", max_length=32, pattern=r"^(OPEN|RESTRICTED|CONFIDENTIAL|SECRET|TOP_SECRET)$")


# ── Dependencia de sesión DB ────────────────────────────────────────

async def get_db():
    async with async_session_factory() as session:
        yield session


# ── ORBAT (Order of Battle) ────────────────────────────────────────

@router.get("/orbat", tags=["C2 / ORBAT"])
async def get_orbat(
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Obtiene jerarquía ORBAT completa."""
    from geoalchemy2.shape import to_shape
    result = await db.execute(select(ORBATUnit).where(ORBATUnit.status != "DELETED"))
    units = result.scalars().all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "type": u.unit_type,
            "parent_id": u.parent_id,
            "status": u.status,
            "location": to_shape(u.location).wkt if u.location is not None else None,
            "classification": u.classification_level
        } for u in units
    ]


@router.post("/orbat/units", tags=["C2 / ORBAT"])
async def create_orbat_unit(
    payload: ORBATUnitIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Crea una nueva unidad en el ORBAT."""
    unit = ORBATUnit(
        id=str(uuid.uuid4()),
        name=payload.name,
        unit_type=payload.unit_type,
        parent_id=payload.parent_id,
        classification_level=payload.classification,
        status="ACTIVE"
    )
    db.add(unit)

    # Event Sourcing: registrar evento
    event = EventStore(
        aggregate_id=unit.id,
        aggregate_type="ORBATUnit",
        event_type="UNIT_CREATED",
        payload={"name": payload.name, "type": payload.unit_type, "parent": payload.parent_id}
    )
    db.add(event)

    await db.commit()
    return {"id": unit.id, "status": "created"}


# ── Misiones ────────────────────────────────────────────────────────

@router.post("/missions", tags=["C2 / Missions"])
async def create_mission(
    payload: MissionIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Crea una nueva misión militar."""
    mission = Mission(
        id=str(uuid.uuid4()),
        name=payload.name,
        mission_type=payload.mission_type,
        orbat_unit_id=payload.orbat_unit_id,
        classification_level=payload.classification,
        description=payload.description,
        status="PLANNED"
    )
    db.add(mission)

    event = EventStore(
        aggregate_id=mission.id,
        aggregate_type="Mission",
        event_type="MISSION_CREATED",
        payload={"name": payload.name, "type": payload.mission_type, "unit": payload.orbat_unit_id},
        actor="system"
    )
    db.add(event)

    await db.commit()
    return {"id": mission.id, "status": "planned"}


@router.get("/missions", tags=["C2 / Missions"])
async def list_missions(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Lista misiones activas."""
    query = select(Mission)
    if status:
        query = query.where(Mission.status == status)
    result = await db.execute(query)
    missions = result.scalars().all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "type": m.mission_type,
            "status": m.status,
            "classification": m.classification_level,
            "start": m.start_time,
            "end": m.end_time
        } for m in missions
    ]


@router.put("/missions/{mission_id}/status", tags=["C2 / Missions"])
async def update_mission_status(
    mission_id: str,
    payload: MissionStatusIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Actualiza estado de misión (PLANNED→ACTIVE→COMPLETED)."""
    await db.execute(
        update(Mission).where(Mission.id == mission_id).values(status=payload.new_status)
    )

    event = EventStore(
        aggregate_id=mission_id,
        aggregate_type="Mission",
        event_type="MISSION_STATUS_CHANGED",
        payload={"new_status": payload.new_status}
    )
    db.add(event)

    await db.commit()
    return {"status": "updated", "mission_id": mission_id}


# ── Blue Force Tracking ─────────────────────────────────────────────

@router.post("/blue-force/report", tags=["C2 / Blue Force"])
async def report_blue_force(
    payload: BlueForceReportIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Reporte de posición Blue Force (amigo)."""
    from geoalchemy2.elements import WKTElement
    position = WKTElement(f"POINT({payload.lon} {payload.lat})", srid=4326)

    report = BlueForceTracking(
        id=str(uuid.uuid4()),
        unit_id=payload.unit_id,
        asset_id=payload.asset_id,
        position=position,
        altitude=payload.altitude,
        heading=payload.heading,
        speed=payload.speed,
        status="ACTIVE",
        timestamp=datetime.utcnow()
    )
    db.add(report)

    # Evento para procesamiento
    event = EventStore(
        aggregate_id=report.id,
        aggregate_type="BlueForce",
        event_type="POSITION_REPORTED",
        payload={"unit": payload.unit_id, "lat": payload.lat, "lon": payload.lon}
    )
    db.add(event)

    await db.commit()
    return {"id": report.id, "status": "reported"}


@router.get("/blue-force/active", tags=["C2 / Blue Force"])
async def get_active_blue_force(
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Obtiene fuerzas amigas activas."""
    from geoalchemy2.shape import to_shape
    result = await db.execute(
        select(BlueForceTracking)
        .where(BlueForceTracking.status == "ACTIVE")
        .order_by(BlueForceTracking.timestamp.desc())
    )
    reports = result.scalars().all()
    return [
        {
            "id": r.id,
            "unit_id": r.unit_id,
            "position": to_shape(r.position).wkt if r.position is not None else None,
            "altitude": r.altitude,
            "heading": r.heading,
            "speed": r.speed,
            "timestamp": r.timestamp
        } for r in reports
    ]


# ── Órdenes (OPORD) ───────────────────────────────────────────────

@router.post("/orders", tags=["C2 / Orders"])
async def issue_order(
    payload: OrderIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Emite una orden de operación (OPORD)."""
    order_id = str(uuid.uuid4())

    event = EventStore(
        aggregate_id=order_id,
        aggregate_type="Order",
        event_type="ORDER_ISSUED",
        payload={
            "mission_id": payload.mission_id,
            "content": payload.content,
            "classification": payload.classification
        },
        actor="commander"
    )
    db.add(event)

    await db.commit()
    return {"order_id": order_id, "status": "issued"}
