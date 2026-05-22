"""
Modelos expandidos para SESIS v3.0 — C2, EW, Cyber, Logistics, Space.
Incluye cifrado AES-256-GCM en campos sensibles.
"""
from sqlalchemy import Column, String, DateTime, Float, JSON, ForeignKey, Integer, Boolean, Text, Enum
from sqlalchemy.orm import relationship, declarative_base
from geoalchemy2 import Geography
import datetime
import uuid
from typing import Optional
from app.core.config import settings

Base = declarative_base()

# ─── Sensitive Data Wrapper ────────────────────────────────────────────────

_cipher = None


def _get_cipher() -> AESCipher:
    global _cipher
    if _cipher is None:
        _cipher = AESCipher.from_hex(settings.AES_KEY)
    return _cipher


class EncryptedField:
    """Descriptor para campos cifrados automáticamente."""

    def __init__(self, column_name: str):
        self.column_name = column_name
        self._cache = {}

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        encrypted = getattr(obj, self.column_name, None)
        if not encrypted:
            return {}
        # Cache para evitar descifrado repetido en misma instancia
        obj_id = id(obj)
        if obj_id not in self._cache:
            try:
                self._cache[obj_id] = _get_cipher().decrypt(encrypted)
            except Exception:
                return {}
        return self._cache[obj_id]

    def __set__(self, obj, value: dict):
        if not isinstance(value, dict):
            raise ValueError("EncryptedField solo acepta dict/JSON")
        encrypted = _get_cipher().encrypt(value)
        setattr(obj, self.column_name, encrypted)
        # Limpiar cache
        obj_id = id(obj)
        if obj_id in self._cache:
            del self._cache[obj_id]


# ─── Modelos Base (legacy) ────────────────────────────────────────────────

class Asset(Base):
    __tablename__ = "assets"

    id = Column(String, primary_key=True)
    kind = Column(String, nullable=False)
    current_status = Column(String)
    last_heartbeat = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    location = Column(Geography(geometry_type="POINT", srid=4326))
    classification_level = Column(String, nullable=False)
    metadata_json = Column(JSON, name="metadata", default={})


class Event(Base):
    __tablename__ = "events"

    event_id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False)
    asset_id = Column(String, ForeignKey("assets.id"), nullable=False)
    ts = Column(DateTime(timezone=True), nullable=False)
    geo_point = Column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    classification_level = Column(String, nullable=False)
    confidence_score = Column(Float, nullable=False)
    payload = Column(JSON, nullable=False)
    signature = Column(JSON, nullable=False)


class Telemetry(Base):
    __tablename__ = "telemetry"

    ts = Column(DateTime(timezone=True), primary_key=True)
    asset_id = Column(String, primary_key=True)
    parameter = Column(String, primary_key=True)
    value = Column(Float, nullable=False)
    unit = Column(String)
    metadata_json = Column(JSON, name="metadata", default={})


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, ForeignKey("events.event_id"))
    rule_id = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    description = Column(String)
    is_anomaly = Column(Boolean, default=False)
    human_validated = Column(Boolean, default=False)
    validated_by = Column(String)
    # Campo cifrado para detalles sensibles
    _sensitive = Column("sensitive", Text, nullable=True)

    sensitive = EncryptedField("_sensitive")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=False)
    context = Column(JSON, default={})
    # Hash chain (CRITICAL-4): cada fila enlaza con la anterior vía sha256(prev_hash || canonical).
    prev_hash = Column(String(64), nullable=False, default="0" * 64)
    row_hash = Column(String(64), nullable=False, default="")


class IntelligenceProduct(Base):
    __tablename__ = "intelligence_products"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_type = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    classification_level = Column(String, nullable=False, default="CONFIDENTIAL")
    source_data = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow)
    created_by = Column(String, nullable=False, default="SYSTEM")


class PriorityIntelligenceRequirement(Base):
    __tablename__ = "priority_intelligence_requirements"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(Integer, nullable=False)
    collection_methods = Column(JSON, default=[])
    due_date = Column(DateTime(timezone=True), nullable=True)
    classification_level = Column(String, nullable=False, default="CONFIDENTIAL")
    created_by = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow())


class SensorSource(Base):
    __tablename__ = "sensor_sources"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sensor_id = Column(String, nullable=False, unique=True)
    sensor_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ACTIVE")
    classification_level = Column(String, nullable=False, default="CONFIDENTIAL")
    first_seen = Column(DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow())
    last_seen = Column(DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow())
    metadata_json = Column(JSON, name="metadata", default={})


class IntelFusionRecord(Base):
    __tablename__ = "intel_fusion_records"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String, nullable=True)
    fusion_score = Column(Float, nullable=False)
    source_count = Column(Integer, nullable=False, default=0)
    correlated_count = Column(Integer, nullable=False, default=0)
    assessment = Column(JSON, default={})
    classification_level = Column(String, nullable=False, default="CONFIDENTIAL")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow())


# ─── NUEVOS MODELOS v3.0 ──────────────────────────────────────────────────

class ORBATUnit(Base):
    """Order of Battle — Jerarquía de unidades militares."""
    __tablename__ = "orbat_units"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_id = Column(String, ForeignKey("orbat_units.id"), nullable=True)
    name = Column(String, nullable=False)
    unit_type = Column(String, nullable=False)  # tierra, mar, aire, espacio, ciber
    classification_level = Column(String, nullable=False, default="CONFIDENTIAL")
    location = Column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    commander_id = Column(String, nullable=True)
    status = Column(String, default="ACTIVE")  # ACTIVE, DEGRADED, OFFLINE
    metadata_json = Column(JSON, name="metadata", default={})


class Mission(Base):
    """Misiones tácticas/estratégicas."""
    __tablename__ = "missions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    mission_type = Column(String, nullable=False)  # OFENSIVA, DEFENSIVA, PEACEKEEPING
    status = Column(String, default="PLANNED")  # PLANNED, ACTIVE, COMPLETED, ABORTED
    classification_level = Column(String, nullable=False, default="SECRET")
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    commander_id = Column(String, nullable=True)
    orbat_unit_id = Column(String, ForeignKey("orbat_units.id"), nullable=True)
    # Datos sensibles cifrados (objetivos, coordenadas, etc.)
    _sensitive = Column("sensitive", Text, nullable=True)
    sensitive = EncryptedField("_sensitive")
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow())
    created_by = Column(String, nullable=False)


class BlueForceTracking(Base):
    """Blue Force Tracking — Amigos en tiempo real."""
    __tablename__ = "blue_force_tracking"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    unit_id = Column(String, ForeignKey("orbat_units.id"), nullable=False)
    asset_id = Column(String, ForeignKey("assets.id"), nullable=True)
    position = Column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    altitude = Column(Float, nullable=True)
    heading = Column(Float, nullable=True)
    speed = Column(Float, nullable=True)
    status = Column(String, default="ACTIVE")
    timestamp = Column(DateTime(timezone=True), default=datetime.datetime.utcnow())


class ElectronicWarfareEvent(Base):
    """Eventos de Guerra Electrónica."""
    __tablename__ = "ew_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String, nullable=False)  # JAMMING, SIGINT, ELINT
    frequency_mhz = Column(Float, nullable=True)
    bandwidth_mhz = Column(Float, nullable=True)
    signal_strength = Column(Float, nullable=True)
    position = Column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    classification_level = Column(String, nullable=False, default="SECRET")
    _analysis = Column("analysis", Text, nullable=True)
    analysis = EncryptedField("_analysis")
    timestamp = Column(DateTime(timezone=True), default=datetime.datetime.utcnow())


class CyberIncident(Base):
    """Incidentes de ciberdefensa."""
    __tablename__ = "cyber_incidents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    incident_type = Column(String, nullable=False)  # MALWARE, DDoS, INTRUSION, etc.
    severity = Column(String, nullable=False)
    source_ip = Column(String, nullable=True)
    target_system = Column(String, nullable=False)
    kill_chain_stage = Column(String, nullable=True)  # RECON, WEAPONIZE, DELIVER, etc.
    classification_level = Column(String, nullable=False, default="SECRET")
    _forensics = Column("forensics", Text, nullable=True)
    forensics = EncryptedField("_forensics")
    status = Column(String, default="OPEN")  # OPEN, INVESTIGATING, CONTAINED, CLOSED
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow())
    created_by = Column(String, nullable=False)


class LogisticsSupply(Base):
    """Cadena de suministro y suministros."""
    __tablename__ = "logistics_supplies"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    item_type = Column(String, nullable=False)  # AMMO_5_56, AMMO_7_62, FUEL, MEDICINE
    quantity = Column(Float, nullable=False)
    unit = Column(String, nullable=False)  # rounds, liters, boxes
    location_id = Column(String, ForeignKey("orbat_units.id"), nullable=True)
    min_threshold = Column(Float, nullable=True)
    classification_level = Column(String, nullable=False, default="CONFIDENTIAL")
    last_updated = Column(DateTime(timezone=True), default=datetime.datetime.utcnow())


class EventStore(Base):
    """Event Sourcing — Registro inmutable de eventos de dominio."""
    __tablename__ = "event_store"

    event_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    aggregate_id = Column(String, nullable=False, index=True)
    aggregate_type = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    metadata_json = Column("metadata", JSON, default={})
    occurred_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow())
    actor = Column(String, nullable=True)
