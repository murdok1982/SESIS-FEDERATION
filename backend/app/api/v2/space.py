"""
Space Domain Awareness API v2.
Conciencia del dominio espacial: satélites, ASAT, SSA.
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
from app.models.persistence import EventStore
from app.core.config import settings

router = APIRouter()


async def get_db():
    async with async_session_factory() as session:
        yield session


class AnomalyType(str, Enum):
    DEORBIT = "DEORBIT"
    SIGNAL_LOSS = "SIGNAL_LOSS"
    MANEUVER = "MANEUVER"
    ASAT_THREAT = "ASAT_THREAT"


class SatelliteAnomalyIn(BaseModel):
    satellite_id: str = Field(..., max_length=64)
    anomaly_type: AnomalyType
    details: Optional[str] = Field(None, max_length=2000)
    classification: str = Field("TOP_SECRET", max_length=32, pattern=r"^(OPEN|RESTRICTED|CONFIDENTIAL|SECRET|TOP_SECRET)$")


class ASATResponseType(str, Enum):
    HARD_KILL = "HARD_KILL"
    SOFT_KILL = "SOFT_KILL"
    EW_COUNTER = "EW_COUNTER"


class ASATResponseIn(BaseModel):
    threat_id: str = Field(..., max_length=64)
    response_type: ASATResponseType
    classification: str = Field("TOP_SECRET", max_length=32, pattern=r"^(OPEN|RESTRICTED|CONFIDENTIAL|SECRET|TOP_SECRET)$")


@router.get("/satellites/tracking", tags=["Space / Satellites"])
async def get_satellite_tracking(
    classification: str = "SECRET",
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Obtiene tracking de satélites propios y extranjeros."""
    # TODO: Integrar con Space-Track.org o sistema nacional
    return {
        "our_satellites": [
            {
                "id": "SAT-001",
                "name": "SENTINEL-1A",
                "norad_id": "12345",
                "orbit_type": "LEO",
                "status": "OPERATIONAL",
                "position": {"lat": 41.0, "lon": 4.0, "alt": 650.0},
                "velocity_kms": 7.8
            },
            {
                "id": "SAT-002",
                "name": "QUANTUM-COMM-3",
                "norad_id": "23456",
                "orbit_type": "GEO",
                "status": "OPERATIONAL",
                "position": {"lat": 0.0, "lon": 4.0, "alt": 35786.0},
                "velocity_kms": 3.07
            }
        ],
        "foreign_tracking": [
            {
                "norad_id": "34567",
                "country": "UNKNOWN",
                "orbit_type": "LEO",
                "status": "MONITORING",
                "threat_assessment": "LOW"
            }
        ],
        "total_tracked": 3,
        "classification": classification
    }


@router.post("/satellites/anomaly", tags=["Space / Anomalies"])
async def report_satellite_anomaly(
    payload: SatelliteAnomalyIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Reporte de anomalía satelital."""
    event_id = str(uuid.uuid4())

    event = EventStore(
        aggregate_id=event_id,
        aggregate_type="SatelliteAnomaly",
        event_type="SATELLITE_ANOMALY",
        payload={
            "satellite_id": payload.satellite_id,
            "anomaly_type": payload.anomaly_type.value,
            "details": payload.details
        },
        actor="space_operator"
    )
    db.add(event)

    await db.commit()
    return {
        "event_id": event_id,
        "status": "anomaly_recorded",
        "response": "ANALYZING" if payload.anomaly_type != AnomalyType.ASAT_THREAT else "DEFENSIVE_MEASURES_ACTIVE",
        "classification": payload.classification
    }


@router.get("/space-situational-awareness", tags=["Space / SSA"])
async def get_ssa_status(
    classification: str = "SECRET",
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Estado de Space Situational Awareness (SSA)."""
    return {
        "space_weather": {
            "solar_activity": "MODERATE",
            "geomagnetic_storm": "KP_3",
            "radiation_belt": "NOMINAL"
        },
        "debris_tracking": {
            "total_objects": 28500,
            "close_approaches_24h": 12,
            "critical_approaches": 1
        },
        "threat_assessment": {
            "asat_capability": "SEVERAL_NATIONS",
            "recent_tests": 0,
            "defensive_posture": "ACTIVE"
        },
        "classification": classification
    }


@router.post("/asat-response", tags=["Space / ASAT"])
async def initiate_asat_response(
    payload: ASATResponseIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("SECRET")),
):
    """Inicia respuesta ante amenaza ASAT (Anti-Satellite)."""
    response_id = str(uuid.uuid4())

    event = EventStore(
        aggregate_id=response_id,
        aggregate_type="ASATResponse",
        event_type="ASAT_RESPONSE_INITIATED",
        payload={
            "threat_id": payload.threat_id,
            "response_type": payload.response_type.value,
            "authorization": "REQUIRED"
        },
        actor="space_command"
    )
    db.add(event)

    await db.commit()
    return {
        "response_id": response_id,
        "status": "awaiting_authorization",
        "response_type": payload.response_type.value,
        "estimated_time": "5-15 minutes",
        "classification": payload.classification
    }
