"""
Multi-source sensor ingestion API.

Handles structured ingestion from:
- Satellite imagery platforms (SAR, Optical, Multispectral, SIGINT-SAT)
- SIGINT/COMINT/ELINT sensors
- HUMINT field operators (SALUTE format)
- Cyber intelligence feeds
- OSINT aggregators
"""
import datetime
import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.db.models.persistence import AuditLog, Event, SensorSource
from app.services.intel_fusion import IntelFusionService

logger = logging.getLogger("sesis.api.sensors")

router = APIRouter()

# ---------------------------------------------------------------------------
# ABAC dependency
# ---------------------------------------------------------------------------

CLEARANCE_ORDER = {
    "OPEN": 0,
    "RESTRICTED": 1,
    "CONFIDENTIAL": 2,
    "SECRET": 3,
    "TOP_SECRET": 4,
}


async def require_operator_key(request: Request) -> dict[str, Any]:
    """Any valid operator API key grants sensor ingestion access."""
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
# Shared sub-schemas
# ---------------------------------------------------------------------------

ClassificationLevel = Literal["OPEN", "RESTRICTED", "CONFIDENTIAL", "SECRET", "TOP_SECRET"]


class GeoPoint(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    altitude_m: float | None = None


# ---------------------------------------------------------------------------
# Ingestion schemas
# ---------------------------------------------------------------------------


class SALUTEReport(BaseModel):
    """
    HUMINT SALUTE report format.
    S – Size  A – Activity  L – Location  U – Unit  T – Time  E – Equipment
    """
    operator_id: str
    mission_id: str
    timestamp: datetime.datetime
    location: GeoPoint
    size: str = Field(..., description="Number/composition of forces")
    activity: str = Field(..., description="What they are doing")
    location_description: str
    unit: str = Field(..., description="Unit identification if known, or UNKNOWN")
    time_observed: datetime.datetime
    equipment: str = Field(..., description="Equipment/vehicles observed")
    classification: ClassificationLevel = "CONFIDENTIAL"
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    additional_notes: str | None = None


class SatelliteProduct(BaseModel):
    satellite_id: str
    product_type: Literal["SAR", "OPTICAL", "MULTISPECTRAL", "SIGINT_SAT", "ELINT_SAT"]
    capture_time: datetime.datetime
    area_of_interest: dict[str, Any] = Field(..., description="GeoJSON polygon")
    resolution_m: float = Field(..., gt=0.0)
    classification: ClassificationLevel = "SECRET"
    url: str = Field(..., description="MinIO/S3 URL to product file")
    metadata: dict[str, Any] = Field(default_factory=dict)
    ai_tags: list[str] = Field(default_factory=list, description="Pre-computed AI tags")


class SIGINTReport(BaseModel):
    sensor_id: str
    sensor_type: Literal["COMINT", "ELINT", "MASINT", "FISINT"]
    timestamp: datetime.datetime
    frequency_mhz: float | None = None
    bearing_deg: float | None = Field(default=None, ge=0.0, le=360.0)
    signal_strength_dbm: float | None = None
    emitter_id: str | None = None
    location: GeoPoint | None = None
    classification: ClassificationLevel = "SECRET"
    raw_data: dict[str, Any] = Field(default_factory=dict)
    analysis: str | None = None
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class CyberAlert(BaseModel):
    sensor_id: str
    alert_type: Literal[
        "INTRUSION", "MALWARE", "EXFILTRATION", "DOS", "APT", "INSIDER_THREAT", "ANOMALY"
    ]
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    timestamp: datetime.datetime
    source_ip: str | None = None
    target_ip: str | None = None
    target_system: str | None = None
    iocs: list[str] = Field(default_factory=list, description="Indicators of Compromise")
    ttps: list[str] = Field(default_factory=list, description="MITRE ATT&CK TTPs")
    classification: ClassificationLevel = "CONFIDENTIAL"
    raw_data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class OSINTIngest(BaseModel):
    source_name: str
    source_url: str | None = None
    collected_at: datetime.datetime
    content: str = Field(..., min_length=1)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    geo_mentions: list[GeoPoint] = Field(default_factory=list)
    classification: ClassificationLevel = "OPEN"
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    language: str = "en"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event_from_salute(report: SALUTEReport, event_id: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": "humint_salute_report",
        "asset_id": report.operator_id,
        "ts": report.timestamp.isoformat(),
        "geo": {"lat": report.location.lat, "lon": report.location.lon},
        "classification_level": report.classification,
        "confidence_score": report.confidence,
        "source_type": "HUMINT",
        "payload": {
            "salute": {
                "size": report.size,
                "activity": report.activity,
                "location": report.location_description,
                "unit": report.unit,
                "time_observed": report.time_observed.isoformat(),
                "equipment": report.equipment,
            },
            "mission_id": report.mission_id,
            "additional_notes": report.additional_notes,
        },
        "signature": {"alg": "OPERATOR_KEY", "sig": "OPERATOR_AUTHENTICATED"},
    }


async def _upsert_sensor_source(
    db: AsyncSession,
    sensor_id: str,
    sensor_type: str,
    classification: str,
    metadata: dict[str, Any],
) -> None:
    """Register or update a sensor source record."""
    try:
        result = await db.execute(
            select(SensorSource).where(SensorSource.sensor_id == sensor_id)
        )
        existing = result.scalars().first()
        now = datetime.datetime.utcnow()

        if existing:
            existing.last_seen = now
            existing.status = "ACTIVE"
        else:
            db.add(
                SensorSource(
                    id=str(uuid.uuid4()),
                    sensor_id=sensor_id,
                    sensor_type=sensor_type,
                    classification_level=classification,
                    status="ACTIVE",
                    metadata_json=metadata,
                    first_seen=now,
                    last_seen=now,
                )
            )
        await db.commit()
    except Exception as exc:
        logger.error("upsert_sensor_source failed: %s", exc)
        await db.rollback()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", summary="Status of all active sensors")
async def sensors_status(
    operator: dict = Depends(require_operator_key),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return all sensor sources and their last activity."""
    operator_level = CLEARANCE_ORDER.get(operator.get("clearance", "OPEN"), 0)
    stmt = select(SensorSource).order_by(desc(SensorSource.last_seen))
    rows = (await db.execute(stmt)).scalars().all()

    sources = []
    for row in rows:
        row_level = CLEARANCE_ORDER.get(row.classification_level, 0)
        if row_level <= operator_level:
            sources.append(
                {
                    "sensor_id": row.sensor_id,
                    "sensor_type": row.sensor_type,
                    "status": row.status,
                    "classification": row.classification_level,
                    "first_seen": row.first_seen.isoformat() if row.first_seen else None,
                    "last_seen": row.last_seen.isoformat() if row.last_seen else None,
                }
            )
    return sources


@router.post("/humint/report", summary="Ingest HUMINT SALUTE report", status_code=202)
async def ingest_humint(
    report: SALUTEReport,
    request: Request,
    operator: dict = Depends(require_operator_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Ingest a HUMINT SALUTE format report from a field operator.
    Triggers intel fusion evaluation.
    """
    event_id = str(uuid.uuid4())
    event_dict = _make_event_from_salute(report, event_id)

    await _upsert_sensor_source(db, report.operator_id, "HUMINT", report.classification, {})

    # Attempt fusion evaluation
    try:
        fusion_svc = IntelFusionService(db)
        fusion = await fusion_svc.fuse_events([{**event_dict, "location": {"lat": report.location.lat, "lon": report.location.lon}}])
        fusion_score = fusion.fusion_score
    except Exception as exc:
        logger.warning("Fusion evaluation failed for HUMINT report: %s", exc)
        fusion_score = 0.0

    await _log_audit(
        db,
        actor=operator.get("name", report.operator_id),
        action="HUMINT_REPORT_INGEST",
        resource_type="SALUTE_REPORT",
        resource_id=event_id,
        context={
            "mission_id": report.mission_id,
            "confidence": report.confidence,
            "fusion_score": fusion_score,
        },
    )

    return {
        "status": "accepted",
        "event_id": event_id,
        "source_type": "HUMINT",
        "fusion_score": fusion_score,
        "received_at": datetime.datetime.utcnow().isoformat(),
    }


@router.post("/satellite/ingest", summary="Ingest satellite imagery product", status_code=202)
async def ingest_satellite(
    product: SatelliteProduct,
    request: Request,
    operator: dict = Depends(require_operator_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Register a satellite intelligence product (SAR, optical, multispectral,
    or SIGINT-SAT) and trigger automated AI tag analysis.
    """
    event_id = str(uuid.uuid4())
    centroid = _extract_centroid(product.area_of_interest)

    await _upsert_sensor_source(
        db,
        product.satellite_id,
        f"SATINT_{product.product_type}",
        product.classification,
        {"resolution_m": product.resolution_m},
    )

    await _log_audit(
        db,
        actor=operator.get("name", product.satellite_id),
        action="SATELLITE_PRODUCT_INGEST",
        resource_type="SATELLITE_PRODUCT",
        resource_id=event_id,
        context={
            "satellite_id": product.satellite_id,
            "product_type": product.product_type,
            "ai_tags": product.ai_tags,
        },
    )

    return {
        "status": "accepted",
        "event_id": event_id,
        "satellite_id": product.satellite_id,
        "product_type": product.product_type,
        "centroid": centroid,
        "ai_tags": product.ai_tags,
        "classification": product.classification,
        "received_at": datetime.datetime.utcnow().isoformat(),
    }


@router.post("/sigint/report", summary="Ingest SIGINT/COMINT/ELINT report", status_code=202)
async def ingest_sigint(
    report: SIGINTReport,
    request: Request,
    operator: dict = Depends(require_operator_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Ingest a SIGINT report and correlate with known emitters."""
    event_id = str(uuid.uuid4())

    await _upsert_sensor_source(
        db,
        report.sensor_id,
        report.sensor_type,
        report.classification,
        {
            "frequency_mhz": report.frequency_mhz,
            "bearing_deg": report.bearing_deg,
        },
    )

    intel_event: dict[str, Any] = {
        "event_id": event_id,
        "source_type": "SIGINT",
        "sensor_type": report.sensor_type,
        "timestamp": report.timestamp.isoformat(),
        "emitter_id": report.emitter_id,
        "confidence": report.confidence,
        "classification": report.classification,
    }
    if report.location:
        intel_event["location"] = {"lat": report.location.lat, "lon": report.location.lon}

    try:
        fusion_svc = IntelFusionService(db)
        fusion = await fusion_svc.fuse_events([intel_event])
        fusion_score = fusion.fusion_score
    except Exception as exc:
        logger.warning("Fusion evaluation failed for SIGINT report: %s", exc)
        fusion_score = 0.0

    await _log_audit(
        db,
        actor=operator.get("name", report.sensor_id),
        action="SIGINT_REPORT_INGEST",
        resource_type="SIGINT_REPORT",
        resource_id=event_id,
        context={
            "sensor_type": report.sensor_type,
            "emitter_id": report.emitter_id,
            "confidence": report.confidence,
        },
    )

    return {
        "status": "accepted",
        "event_id": event_id,
        "source_type": "SIGINT",
        "sensor_type": report.sensor_type,
        "fusion_score": fusion_score,
        "received_at": datetime.datetime.utcnow().isoformat(),
    }


@router.post("/cyber/alert", summary="Ingest cyber intelligence alert", status_code=202)
async def ingest_cyber_alert(
    alert: CyberAlert,
    request: Request,
    operator: dict = Depends(require_operator_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Ingest a cyber intelligence alert (intrusion, APT, malware, etc.).
    HIGH and CRITICAL alerts are immediately routed through intel fusion.
    """
    event_id = str(uuid.uuid4())

    await _upsert_sensor_source(
        db,
        alert.sensor_id,
        "CYBER",
        alert.classification,
        {"alert_type": alert.alert_type},
    )

    intel_event: dict[str, Any] = {
        "event_id": event_id,
        "source_type": "CYBER",
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "timestamp": alert.timestamp.isoformat(),
        "iocs": alert.iocs,
        "ttps": alert.ttps,
        "confidence": alert.confidence,
        "classification": alert.classification,
    }

    fusion_score = 0.0
    if alert.severity in ("HIGH", "CRITICAL"):
        try:
            fusion_svc = IntelFusionService(db)
            fusion = await fusion_svc.fuse_events([intel_event])
            fusion_score = fusion.fusion_score
        except Exception as exc:
            logger.warning("Fusion evaluation failed for CYBER alert: %s", exc)

    await _log_audit(
        db,
        actor=operator.get("name", alert.sensor_id),
        action="CYBER_ALERT_INGEST",
        resource_type="CYBER_ALERT",
        resource_id=event_id,
        context={
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "ioc_count": len(alert.iocs),
        },
    )

    return {
        "status": "accepted",
        "event_id": event_id,
        "source_type": "CYBER",
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "fusion_score": fusion_score,
        "received_at": datetime.datetime.utcnow().isoformat(),
    }


@router.post("/osint/ingest", summary="Ingest OSINT report", status_code=202)
async def ingest_osint(
    report: OSINTIngest,
    request: Request,
    operator: dict = Depends(require_operator_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Ingest an open-source intelligence report. Entity extraction and
    geo-tagging are accepted as pre-processed fields.
    """
    event_id = str(uuid.uuid4())

    intel_event: dict[str, Any] = {
        "event_id": event_id,
        "source_type": "OSINT",
        "source_name": report.source_name,
        "timestamp": report.collected_at.isoformat(),
        "confidence": report.confidence,
        "classification": report.classification,
        "entities": report.entities,
        "tags": report.tags,
    }
    if report.geo_mentions:
        intel_event["location"] = {
            "lat": report.geo_mentions[0].lat,
            "lon": report.geo_mentions[0].lon,
        }

    await _log_audit(
        db,
        actor=operator.get("name", "OSINT_FEED"),
        action="OSINT_INGEST",
        resource_type="OSINT_REPORT",
        resource_id=event_id,
        context={
            "source": report.source_name,
            "entity_count": len(report.entities),
            "tag_count": len(report.tags),
        },
    )

    return {
        "status": "accepted",
        "event_id": event_id,
        "source_type": "OSINT",
        "source_name": report.source_name,
        "classification": report.classification,
        "received_at": datetime.datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Geo utilities
# ---------------------------------------------------------------------------


def _extract_centroid(geojson: dict[str, Any]) -> dict[str, float] | None:
    """
    Compute centroid of a GeoJSON polygon by averaging all coordinate pairs.
    Returns {"lat": ..., "lon": ...} or None on failure.
    """
    try:
        coords: list[list[float]] = []
        geometry = geojson.get("geometry", geojson)
        geom_type = geometry.get("type", "")
        raw_coords = geometry.get("coordinates", [])

        if geom_type == "Polygon" and raw_coords:
            coords = raw_coords[0]  # exterior ring
        elif geom_type == "MultiPolygon" and raw_coords:
            coords = raw_coords[0][0]
        else:
            return None

        if not coords:
            return None

        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return {"lat": sum(lats) / len(lats), "lon": sum(lons) / len(lons)}
    except Exception:
        return None
