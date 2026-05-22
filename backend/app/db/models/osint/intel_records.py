from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.osint.base import BaseModel

class TokenBlacklist(BaseModel):
    __tablename__ = "token_blacklist"

    jti: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token_type: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

class AuditChainEntry(BaseModel):
    __tablename__ = "audit_chain"

    index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    previous_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    hash_value: Mapped[str] = mapped_column(String(256), nullable=False, index=True)

class ChainOfCustodyRecord(BaseModel):
    __tablename__ = "chain_of_custody"

    evidence_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    evidence_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collected_by: Mapped[str] = mapped_column(String(36), nullable=False)
    custody_chain: Mapped[list | None] = mapped_column(JSON, nullable=True)
    integrity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_verification: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class IntelligenceFusionRecord(BaseModel):
    __tablename__ = "intelligence_fusion"

    fusion_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(256), nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    input_sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    correlated_entities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    relationships_found: Mapped[list | None] = mapped_column(JSON, nullable=True)
    threat_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    recommendations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    graph_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    classification: Mapped[str] = mapped_column(String(32), nullable=False, default="UNCLASSIFIED")

class STIXObjectRecord(BaseModel):
    __tablename__ = "stix_objects"

    stix_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    stix_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    labels: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    modified: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    properties: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    kill_chain_phases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    external_references: Mapped[list | None] = mapped_column(JSON, nullable=True)
