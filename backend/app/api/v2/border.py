"""
Border & Maritime Control API v2.
Control fronterizo, ADIZ (Air Defense ID Zone), dominio marítimo.
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
from app.models.persistence import EventStore, Asset
from app.core.config import settings

router = APIRouter()


async def get_db():
    async with async_session_factory() as session:
        yield session


class PerimeterEventType(str, Enum):
    INTRUSION = "INTRUSION"
    MOVEMENT = "MOVEMENT"
    BREACH = "BREACH"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PerimeterSensorIn(BaseModel):
    sensor_id: str = Field(..., max_length=64)
    event_type: PerimeterEventType
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    severity: Severity = Severity.MEDIUM
    classification: str = Field("CONFIDENTIAL", max_length=32, pattern=r"^(OPEN|RESTRICTED|CONFIDENTIAL|SECRET|TOP_SECRET)$")


class ADIZIn(BaseModel):
    aircraft_id: str = Field(..., max_length=64)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    altitude: float
    speed: float = Field(..., ge=0.0)
    heading: float = Field(..., ge=0.0, le=360.0)
    classification: str = Field("SECRET", max_length=32, pattern=r"^(OPEN|RESTRICTED|CONFIDENTIAL|SECRET|TOP_SECRET)$")


class InterdictionIn(BaseModel):
    vessel_mmsi: str = Field(..., max_length=32, pattern=r"^[0-9]+$")
    reason: str = Field(..., max_length=64, pattern=r"^[A-Z_]+$")
    classification: str = Field("SECRET", max_length=32, pattern=r"^(OPEN|RESTRICTED|CONFIDENTIAL|SECRET|TOP_SECRET)$")


@router.post("/perimeter-sensor", tags=["Border / Sensors"])
async def report_perimeter_event(
    payload: PerimeterSensorIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("CONFIDENTIAL")),
):
    """Reporte de sensor perimetral fronterizo."""
    event_id = str(uuid.uuid4())
    event = EventStore(
        aggregate_id=event_id,
        aggregate_type="BorderSensor",
        event_type="PERIMETER_ALERT",
        payload={
            "sensor_id": payload.sensor_id,
            "event_type": payload.event_type.value,
            "position": f"{payload.lat},{payload.lon}",
            "severity": payload.severity.value
        }
    )
    db.add(event)

    await db.commit()
    return {"event_id": event_id, "status": "recorded", "classification": payload.classification}


@router.get("/perimeter-status", tags=["Border / Status"])
async def get_perimeter_status(
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("CONFIDENTIAL")),
):
    """Estado del perímetro fronterizo."""
    # TODO: Conectar con sensores reales
    return {
        "sectors": [
            {"name": "NORTE", "status": "SECURE", "sensors_active": 12, "alerts_24h": 3},
            {"name": "SUR", "status": "ELEVATED", "sensors_active": 8, "alerts_24h": 7},
            {"name": "ESTE", "status": "SECURE", "sensors_active": 15, "alerts_24h": 1},
            {"name": "OESTE", "status": "MONITORING", "sensors_active": 10, "alerts_24h": 4}
        ],
        "total_sensors": 45,
        "active_sensors": 42,
        "alerts_last_24h": 15
    }


@router.post("/adiz-violation", tags=["Border / ADIZ"])
async def report_adiz_violation(
    payload: ADIZIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("CONFIDENTIAL")),
):
    """Reporte de violación de ADIZ (Air Defense Identification Zone)."""
    event_id = str(uuid.uuid4())

    event = EventStore(
        aggregate_id=event_id,
        aggregate_type="ADIZ",
        event_type="ADIZ_VIOLATION",
        payload={
            "aircraft_id": payload.aircraft_id,
            "position": f"{payload.lat},{payload.lon},{payload.altitude}",
            "speed": payload.speed,
            "heading": payload.heading,
            "violation_type": "UNAUTHORIZED_ENTRY"
        }
    )
    db.add(event)

    await db.commit()
    return {
        "event_id": event_id,
        "status": "violation_recorded",
        "response": "INTERCEPTOR_DISPATCHED",
        "classification": payload.classification
    }


@router.get("/maritime-tracks", tags=["Maritime / AIS"])
async def get_maritime_tracks(
    zone: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("CONFIDENTIAL")),
):
    """Obtiene tracks marítimos (AIS) en zona económica exclusiva."""
    # TODO: Integrar con AIS real
    return {
        "zone": zone or "EEZ_COMPLETE",
        "vessels": [
            {
                "mmsi": "123456789",
                "name": "BUQUE PESQUERO 1",
                "type": "FISHING",
                "position": "41.0N,4.5W",
                "speed": 8.5,
                "course": 180,
                "status": "MONITORED"
            },
            {
                "mmsi": "987654321",
                "name": "CARGA INTERNACIONAL",
                "type": "CARGO",
                "position": "40.5N,3.8W",
                "speed": 12.0,
                "course": 270,
                "status": "CLEARED"
            }
        ],
        "total_tracks": 2,
        "alerts": 0
    }


@router.post("/maritime-interdiction", tags=["Maritime / Operations"])
async def initiate_maritime_interdiction(
    payload: InterdictionIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("CONFIDENTIAL")),
):
    """Inicia interdicción marítima."""
    interdiction_id = str(uuid.uuid4())

    event = EventStore(
        aggregate_id=interdiction_id,
        aggregate_type="MaritimeInterdiction",
        event_type="INTERDICTION_STARTED",
        payload={
            "vessel_mmsi": payload.vessel_mmsi,
            "reason": payload.reason,
            "force_used": "MINIMAL"
        }
    )
    db.add(event)

    await db.commit()
    return {
        "interdiction_id": interdiction_id,
        "status": "initiated",
        "response_units": ["COAST_GUARD_PATROL_1", "NAVAL_UNIT_3"],
        "classification": payload.classification
    }
