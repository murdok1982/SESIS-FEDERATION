from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import get_db

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class UUIDMixin:
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

class BaseModel(UUIDMixin, TimestampMixin, Base):
    __abstract__ = True
