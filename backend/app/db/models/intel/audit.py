"""
Tamper-evident audit log model.

Each :class:`AuditEvent` row contains:
    * Actor identification (user id, IP, user agent).
    * Event type (``auth.login``, ``classified.read``, ``llm.dispatch``...).
    * Resource reference and classification when applicable.
    * Outcome (``success`` / ``denied`` / ``error``).
    * Free-form ``metadata_json`` for IDs, status codes and latency.
      The metadata MUST NOT contain prompts, completions, OTP codes,
      passwords or any other sensitive payload.

The chain is anchored with two hash columns:

    prev_hash : sha256 of the immediately preceding row.
    row_hash  : sha256(prev_hash || canonical_json(this_row)).

The migration installs a trigger that forbids UPDATE and DELETE on
this table (except when issued by the ``app_bypass_rls`` role with
``BYPASSRLS`` set), so the chain can only grow.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.orm import declarative_base
Base = declarative_base()


# ---------------------------------------------------------------------------
# Genesis constants
# ---------------------------------------------------------------------------
# The chain is seeded by the 0002 migration with these exact values so
# the application can verify them at startup without race conditions.
GENESIS_PREV_HASH = "0" * 64
GENESIS_ROW_HASH = (
    # sha256("GENESIS"), precomputed and pinned so both the migration
    # and the verifier agree without recomputing on every import.
    # python -c "import hashlib; print(hashlib.sha256(b'GENESIS').hexdigest())"
    "901131d838b17aac0f7885b81e03cbdc9f5157a00343d30ab22083685ed1416a"
)
GENESIS_EVENT_TYPE = "audit.genesis"


class AuditEvent(Base):
    """Append-only audit log entry."""

    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    actor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    actor_ip = Column(String(45), nullable=True)
    actor_user_agent = Column(String, nullable=True)
    event_type = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=True)
    resource_id = Column(String, nullable=True, index=True)
    classification = Column(Integer, nullable=True)
    org_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    outcome = Column(String, nullable=False)
    metadata_json = Column(JSON, nullable=True)

    # Hash chain — both columns are filled by AuditService.record().
    prev_hash = Column(String(64), nullable=False)
    row_hash = Column(String(64), nullable=False, unique=True)


__all__ = [
    "AuditEvent",
    "GENESIS_PREV_HASH",
    "GENESIS_ROW_HASH",
    "GENESIS_EVENT_TYPE",
]
