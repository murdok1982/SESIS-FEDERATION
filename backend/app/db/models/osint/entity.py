from __future__ import annotations

from enum import Enum

from sqlalchemy import ARRAY, JSON, Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.osint.base import BaseModel

class EntityType(str, Enum):
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    DOMAIN = "DOMAIN"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    IP = "IP"
    ASN = "ASN"
    HANDLE = "HANDLE"
    CHANNEL = "CHANNEL"
    URL = "URL"
    DOCUMENT = "DOCUMENT"
    IMAGE = "IMAGE"
    LOCATION = "LOCATION"
    ALIAS = "ALIAS"

class Entity(BaseModel):
    __tablename__ = "entities"

    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), default="")
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    is_target: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    merged_into_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"), nullable=True)
    source_finding_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    case: Mapped["Case"] = relationship("Case", back_populates="entities")  # type: ignore[name-defined]  # noqa: F821
    merged_into: Mapped["Entity | None"] = relationship("Entity", remote_side="Entity.id")
    evidence: Mapped[list["Evidence"]] = relationship("Evidence", back_populates="entity")  # type: ignore[name-defined]  # noqa: F821
