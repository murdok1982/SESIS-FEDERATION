from __future__ import annotations

from enum import Enum

from sqlalchemy import ARRAY, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.osint.base import BaseModel

class CaseStatus(str, Enum):
    OPEN = "OPEN"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"

class CasePriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class CaseClassification(str, Enum):
    UNCLASSIFIED = "UNCLASSIFIED"
    RESTRICTED = "RESTRICTED"
    CONFIDENTIAL = "CONFIDENTIAL"

class Case(BaseModel):
    __tablename__ = "cases"

    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default=CaseStatus.OPEN, nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), default=CasePriority.MEDIUM, nullable=False, index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    operator_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    scope_notes: Mapped[str] = mapped_column(Text, default="")
    classification: Mapped[str] = mapped_column(String(32), default=CaseClassification.UNCLASSIFIED)
    deleted: Mapped[bool] = mapped_column(default=False)

    operator: Mapped["User"] = relationship("User", back_populates="cases")  # type: ignore[name-defined]  # noqa: F821
    entities: Mapped[list["Entity"]] = relationship("Entity", back_populates="case", cascade="all, delete-orphan")  # type: ignore[name-defined]  # noqa: F821
    evidence: Mapped[list["Evidence"]] = relationship("Evidence", back_populates="case", cascade="all, delete-orphan")  # type: ignore[name-defined]  # noqa: F821
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="case", cascade="all, delete-orphan")  # type: ignore[name-defined]  # noqa: F821
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="case", cascade="all, delete-orphan")  # type: ignore[name-defined]  # noqa: F821
