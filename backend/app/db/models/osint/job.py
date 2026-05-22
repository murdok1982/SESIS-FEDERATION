from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.osint.base import BaseModel

class JobType(str, Enum):
    COORDINATOR = "COORDINATOR"
    OSINT = "OSINT"
    SOCMINT = "SOCMINT"
    ENTITY_RESOLUTION = "ENTITY_RESOLUTION"
    SOURCE_VALIDATION = "SOURCE_VALIDATION"
    REPORT_GENERATION = "REPORT_GENERATION"
    OSINT_RESEARCH = "OSINT_RESEARCH"
    DOMAIN_INVESTIGATION = "DOMAIN_INVESTIGATION"
    CUSTOM = "CUSTOM"

class JobStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PENDING_APPROVAL = "PENDING_APPROVAL"

class Job(BaseModel):
    __tablename__ = "jobs"

    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.PENDING, nullable=False, index=True)
    arq_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str] = mapped_column(String(256), default="")
    task_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    findings_count: Mapped[int] = mapped_column(Integer, default=0)
    input_params: Mapped[dict] = mapped_column(JSON, default=dict)
    output_refs: Mapped[dict] = mapped_column(JSON, default=dict)

    case: Mapped["Case"] = relationship("Case", back_populates="jobs")  # type: ignore[name-defined]  # noqa: F821
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="job")  # type: ignore[name-defined]  # noqa: F821
