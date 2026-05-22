"""
Electronic Warfare (EW) API v2.
Gestión de espectro RF, jamming, detección de emisores.
"""
from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from datetime import datetime
import uuid

from pydantic import BaseModel, Field

from app.db.session import async_session_factory
from app.models.persistence import ElectronicWarfareEvent, EventStore
from app.core.config import settings

router = APIRouter()


async def get_db():
    async with async_session_factory() as session:
        yield session


class EWEventType(str, Enum):
    JAMMING = "JAMMING"
    SIGINT = "SIGINT"
    ELINT = "ELINT"


class RFScanIn(BaseModel):
    event_type: EWEventType
    frequency_mhz: float = Field(..., ge=0.0, le=1_000_000.0)
    bandwidth_mhz: Optional[float] = Field(None, ge=0.0, le=100_000.0)
    signal_strength: Optional[float] = None
    lat: Optional[float] = Field(None, ge=-90.0, le=90.0)
    lon: Optional[float] = Field(None, ge=-180.0, le=180.0)
    classification: str = Field("SECRET", max_length=32, pattern=r"^(OPEN|RESTRICTED|CONFIDENTIAL|SECRET|TOP_SECRET)$")


class JammingIn(BaseModel):
    target_frequency: float = Field(..., ge=0.0, le=1_000_000.0)
    bandwidth: float = Field(..., ge=0.0, le=100_000.0)
    duration_seconds: int = Field(..., ge=1, le=86400)
    location_id: Optional[str] = Field(None, max_length=64)


@router.post("/scans", tags=["EW / Spectrum"])
async def report_rf_scan(
    payload: RFScanIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Reporte de escaneo del espectro RF."""
    from geoalchemy2.elements import WKTElement
    position = None
    if payload.lat is not None and payload.lon is not None:
        position = WKTElement(f"POINT({payload.lon} {payload.lat})", srid=4326)

    event = ElectronicWarfareEvent(
        id=str(uuid.uuid4()),
        event_type=payload.event_type.value,
        frequency_mhz=payload.frequency_mhz,
        bandwidth_mhz=payload.bandwidth_mhz,
        signal_strength=payload.signal_strength,
        position=position,
        classification_level=payload.classification,
        timestamp=datetime.utcnow()
    )
    db.add(event)

    # Event Sourcing
    store_event = EventStore(
        aggregate_id=event.id,
        aggregate_type="EWEvent",
        event_type="RF_SCAN_REPORTED",
        payload={
            "type": payload.event_type.value,
            "freq": payload.frequency_mhz,
            "strength": payload.signal_strength
        }
    )
    db.add(store_event)

    await db.commit()
    return {"id": event.id, "status": "recorded"}


@router.get("/scans", tags=["EW / Spectrum"])
async def list_rf_scans(
    event_type: Optional[str] = None,
    min_freq: Optional[float] = None,
    max_freq: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Lista escaneos RF registrados."""
    from geoalchemy2.shape import to_shape
    query = select(ElectronicWarfareEvent)
    if event_type:
        query = query.where(ElectronicWarfareEvent.event_type == event_type)
    if min_freq:
        query = query.where(ElectronicWarfareEvent.frequency_mhz >= min_freq)
    if max_freq:
        query = query.where(ElectronicWarfareEvent.frequency_mhz <= max_freq)

    result = await db.execute(query.order_by(ElectronicWarfareEvent.timestamp.desc()))
    events = result.scalars().all()

    return [
        {
            "id": e.id,
            "type": e.event_type,
            "frequency_mhz": e.frequency_mhz,
            "bandwidth_mhz": e.bandwidth_mhz,
            "signal_strength": e.signal_strength,
            "position": to_shape(e.position).wkt if e.position is not None else None,
            "timestamp": e.timestamp,
            "classification": e.classification_level
        } for e in events
    ]


@router.post("/jamming/activate", tags=["EW / Jamming"])
async def activate_jamming(
    payload: JammingIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Activa jamming en frecuencia específica."""
    event = ElectronicWarfareEvent(
        id=str(uuid.uuid4()),
        event_type="JAMMING_ACTIVE",
        frequency_mhz=payload.target_frequency,
        bandwidth_mhz=payload.bandwidth,
        classification_level="SECRET",
        timestamp=datetime.utcnow()
    )
    db.add(event)

    store_event = EventStore(
        aggregate_id=event.id,
        aggregate_type="Jamming",
        event_type="JAMMING_ACTIVATED",
        payload={
            "frequency": payload.target_frequency,
            "bandwidth": payload.bandwidth,
            "duration": payload.duration_seconds
        },
        actor="ew_operator"
    )
    db.add(store_event)

    await db.commit()
    return {
        "id": event.id,
        "status": "active",
        "frequency": payload.target_frequency,
        "expires_in": payload.duration_seconds
    }


@router.get("/threat-emitters", tags=["EW / Threats"])
async def get_threat_emitters(
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Identifica emisores hostiles basado en patrones."""
    from geoalchemy2.shape import to_shape
    # Análisis simplificado: frecuencias con múltiples reportes
    query = select(ElectronicWarfareEvent).where(
        ElectronicWarfareEvent.event_type.in_(["SIGINT", "ELINT"])
    ).order_by(ElectronicWarfareEvent.frequency_mhz)

    result = await db.execute(query)
    events = result.scalars().all()

    # Agrupar por frecuencia
    freq_map = {}
    for e in events:
        freq = e.frequency_mhz
        if freq not in freq_map:
            freq_map[freq] = {"count": 0, "types": set(), "positions": []}
        freq_map[freq]["count"] += 1
        freq_map[freq]["types"].add(e.event_type)
        if e.position is not None:
            freq_map[freq]["positions"].append(to_shape(e.position).wkt)

    # Identificar amenazas (frecuencias con >3 reportes)
    threats = []
    for freq, data in freq_map.items():
        if data["count"] >= 3:
            threats.append({
                "frequency_mhz": freq,
                "report_count": data["count"],
                "types": list(data["types"]),
                "sample_positions": data["positions"][:3],
                "threat_level": "HIGH" if data["count"] > 10 else "MEDIUM"
            })

    return {"threat_emitters": threats, "total": len(threats)}
