from sqlalchemy import Column, String, ForeignKey, DateTime, Boolean, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from sqlalchemy.orm import declarative_base
Base = declarative_base()

from app.core.classification import ClassificationLevel, TLPMarker, TLPMarker as TLP


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    country_id = Column(UUID(as_uuid=True), ForeignKey("countries.id"))
    report_date = Column(DateTime, default=datetime.utcnow)
    executive_summary = Column(Text, nullable=False)
    content_json = Column(Text, nullable=False)  # Structural UI representation.
    published = Column(Boolean, default=False)
    # Classification / handling.
    classification = Column(
        Integer,
        nullable=False,
        default=ClassificationLevel.PUBLIC.value,
        server_default=ClassificationLevel.PUBLIC.value,
        index=True,
    )
    tlp = Column(
        String,
        nullable=False,
        default=TLPMarker.CLEAR.value,
        server_default=TLPMarker.CLEAR.value,
    )
    org_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    # Detached Ed25519 signature over the canonical payload.
    # Format: base64( raw_sig_64 || b'|' || fingerprint_16_hex ).
    # Populated by /reports/{id}/publish only.
    signature = Column(Text, nullable=True)
    signed_at = Column(DateTime, nullable=True)
    # 16-hex fingerprint of the public key that produced ``signature``.
    # Indexed so the platform can audit / revoke a specific key.
    signature_fingerprint = Column(
        String(16), nullable=True, index=True
    )


class PremiumReport(Base):
    __tablename__ = "premium_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    request_topic = Column(String, nullable=False)
    content_markdown = Column(Text, nullable=False)
    human_reviewed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Classification / handling.
    classification = Column(
        Integer,
        nullable=False,
        default=ClassificationLevel.PUBLIC.value,
        server_default=ClassificationLevel.PUBLIC.value,
        index=True,
    )
    tlp = Column(
        String,
        nullable=False,
        default=TLPMarker.CLEAR.value,
        server_default=TLPMarker.CLEAR.value,
    )
    org_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    signature = Column(Text, nullable=True)
    signed_at = Column(DateTime, nullable=True)
    signature_fingerprint = Column(
        String(16), nullable=True, index=True
    )


class ReportCitation(Base):
    __tablename__ = "report_citations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_registry_id = Column(UUID(as_uuid=True), ForeignKey("source_registry.id"))
    report_type = Column(String, nullable=False)  # 'daily' or 'premium'
    report_id = Column(UUID(as_uuid=True), nullable=False)
