from __future__ import annotations

from enum import Enum

from sqlalchemy import ARRAY, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.osint.base import BaseModel

class ReportType(str, Enum):
    ENTITY_PROFILE = "entity_profile"
    DOMAIN_INVESTIGATION = "domain_investigation"
    CAMPAIGN_ANALYSIS = "campaign_analysis"
    DIGITAL_PRESENCE = "digital_presence"
    EXECUTIVE_SUMMARY = "executive_summary"
    TECHNICAL_REPORT = "technical_report"

class ReportFormat(str, Enum):
    MARKDOWN = "MARKDOWN"
    PDF = "PDF"
    JSON = "JSON"

class Report(BaseModel):
    __tablename__ = "reports"

    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    report_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(16), default=ReportFormat.MARKDOWN)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_by: Mapped[str] = mapped_column(String(256), default="")
    template_used: Mapped[str] = mapped_column(String(128), default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    entity_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    case: Mapped["Case"] = relationship("Case", back_populates="reports")  # type: ignore[name-defined]  # noqa: F821
    job: Mapped["Job | None"] = relationship("Job", back_populates="reports")  # type: ignore[name-defined]  # noqa: F821
