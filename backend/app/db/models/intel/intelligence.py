from sqlalchemy import Column, String, ForeignKey, DateTime, Float, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from sqlalchemy.orm import declarative_base
Base = declarative_base()

from app.core.classification import ClassificationLevel, TLPMarker


class IntelligenceCategory(Base):
    __tablename__ = "intelligence_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)  # Economic, Political, Military, Social, Security.


class IntelligenceItem(Base):
    __tablename__ = "intelligence_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    country_id = Column(UUID(as_uuid=True), ForeignKey("countries.id"))
    category_id = Column(UUID(as_uuid=True), ForeignKey("intelligence_categories.id"))
    agent_source = Column(String, nullable=False)  # e.g. osint_agent, public_signals, contributor
    content = Column(String, nullable=False)  # Structured markdown or plain text
    confidence_score = Column(Float, default=0.0)  # 0.0 to 1.0
    metadata_json = Column(JSON, nullable=True)
    # Classification / handling tags. Defaults are the most permissive
    # so existing rows survive the migration unchanged.
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
    # NATO Admiralty (STANAG 2511) rating, stored as their raw codes
    # (A-F / 1-6) for readability in operational queries.
    admiralty_reliability = Column(String(1), nullable=True)
    admiralty_credibility = Column(Integer, nullable=True)
    # Tenant scope — NULL means broadcast / cross-org.
    org_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SourceRegistry(Base):
    __tablename__ = "source_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(String, unique=True, nullable=False)
    source_type = Column(String, nullable=False)  # e.g. news, official, social
    credibility_score = Column(Float, default=0.5)
    last_scraped = Column(DateTime, nullable=True)
    # Hard cap on the classification this source can produce.
    # Public OSINT sources stay at PUBLIC; classified feeds may go higher.
    max_classification = Column(
        Integer,
        nullable=False,
        default=ClassificationLevel.PUBLIC.value,
        server_default=ClassificationLevel.PUBLIC.value,
    )
