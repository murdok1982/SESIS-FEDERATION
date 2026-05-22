from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import ARRAY, JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.osint.base import BaseModel

class EvidenceType(str, Enum):
    URL = "URL"
    FILE = "FILE"
    SCREENSHOT = "SCREENSHOT"
    TEXT = "TEXT"
    METADATA = "METADATA"
    API_RESPONSE = "API_RESPONSE"
    DNS_RECORD = "DNS_RECORD"
    WHOIS = "WHOIS"
    CERTIFICATE = "CERTIFICATE"
    SOCIAL_POST = "SOCIAL_POST"
    DOCUMENT = "DOCUMENT"

class Evidence(BaseModel):
    __tablename__ = "evidence"

    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(128), default="", index=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collected_by: Mapped[str] = mapped_column(String(256), default="")
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.7)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)

    case: Mapped["Case"] = relationship("Case", back_populates="evidence")  # type: ignore[name-defined]  # noqa: F821
    entity: Mapped["Entity | None"] = relationship("Entity", back_populates="evidence")  # type: ignore[name-defined]  # noqa: F821
