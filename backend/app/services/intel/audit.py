"""
Tamper-evident audit log service.

Provides two operations:
    * :meth:`AuditService.record` — append one entry. Reads the latest
      ``row_hash``, computes a new one over the canonical JSON of the
      event, and inserts. A Postgres advisory lock serializes
      concurrent inserts so the chain cannot fork.
    * :meth:`AuditService.verify_chain` — walks the table in order
      and recomputes every hash. Returns the first broken id, if any.

The service NEVER stores prompts, completion text, OTP codes,
passwords or any other sensitive payload. Metadata is intended for
short identifiers (request id, status code, latency, provider name).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.classification import ClassificationLevel, TLPMarker
from app.db.models.intel.audit import (
    AuditEvent,
    GENESIS_PREV_HASH,
    GENESIS_ROW_HASH,
)

logger = logging.getLogger(__name__)

# Stable arbitrary 64-bit constant used by pg_advisory_xact_lock. Chosen
# from /dev/urandom and pinned so every backend instance contends for the
# same lock. Don't reuse across unrelated subsystems.
_AUDIT_ADVISORY_LOCK_KEY = 7459_2310_4885_1207


def _canonical(event: dict) -> bytes:
    """Canonical JSON serialization for the hash chain.

    Keys are sorted, separators are tight, ``default=str`` covers
    ``UUID`` / ``datetime`` / ``Decimal``. The output is deterministic
    across Python versions and platforms.
    """
    return json.dumps(
        event,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    ).encode("utf-8")


def _compute_hash(prev_hash: str, event: dict) -> str:
    """Return ``sha256(prev_hash || "|" || canonical(event))`` as hex."""
    h = hashlib.sha256()
    h.update(prev_hash.encode("ascii"))
    h.update(b"|")
    h.update(_canonical(event))
    return h.hexdigest()


class AuditService:
    """Append-only audit log writer + verifier."""

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    async def record(
        self,
        db: AsyncSession,
        *,
        event_type: str,
        actor_user_id: Optional[UUID | str] = None,
        actor_ip: Optional[str] = None,
        actor_user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        classification: Optional[int | ClassificationLevel] = None,
        org_id: Optional[UUID | str] = None,
        outcome: str = "success",
        metadata: Optional[dict] = None,
    ) -> AuditEvent:
        """Append a single event to the chain.

        The function does NOT commit the surrounding transaction — the
        caller controls atomicity.  Callers that need standalone
        durability (middleware, background workers) should commit
        immediately after ``record``.
        """
        if outcome not in {"success", "denied", "error"}:
            outcome = "error"

        # Try to take an advisory lock so concurrent writers serialize.
        # On SQLite (tests) the function is missing — fall back to a
        # no-op silently.
        try:
            await db.execute(
                text("SELECT pg_advisory_xact_lock(:k)"),
                {"k": _AUDIT_ADVISORY_LOCK_KEY},
            )
        except Exception:
            # Non-Postgres dialect (e.g. SQLite in tests). Concurrency
            # in tests is single-threaded so this is acceptable.
            pass

        prev_hash = await self._get_last_hash(db)

        ts = datetime.now(timezone.utc)
        event_id = uuid4()
        cls_int: Optional[int]
        if classification is None:
            cls_int = None
        elif isinstance(classification, ClassificationLevel):
            cls_int = int(classification)
        else:
            cls_int = int(classification)

        # Canonical body used to compute the hash. The id and the
        # timestamp are included so that re-running the chain
        # verification on a dumped table yields the same hashes.
        canonical_body = {
            "id": str(event_id),
            "timestamp": ts.isoformat(),
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "actor_ip": actor_ip,
            "actor_user_agent": actor_user_agent,
            "event_type": event_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "classification": cls_int,
            "org_id": str(org_id) if org_id else None,
            "outcome": outcome,
            "metadata_json": metadata or None,
        }
        row_hash = _compute_hash(prev_hash, canonical_body)

        event = AuditEvent(
            id=event_id,
            timestamp=ts,
            actor_user_id=UUID(str(actor_user_id)) if actor_user_id else None,
            actor_ip=actor_ip,
            actor_user_agent=actor_user_agent,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            classification=cls_int,
            org_id=UUID(str(org_id)) if org_id else None,
            outcome=outcome,
            metadata_json=metadata or None,
            prev_hash=prev_hash,
            row_hash=row_hash,
        )
        db.add(event)
        await db.flush()
        return event

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    async def _get_last_hash(self, db: AsyncSession) -> str:
        """Return the row_hash of the most recent event, or the genesis."""
        stmt = (
            select(AuditEvent.row_hash)
            .order_by(AuditEvent.timestamp.desc(), AuditEvent.id.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        last = result.scalar_one_or_none()
        return last or GENESIS_ROW_HASH

    async def verify_chain(
        self,
        db: AsyncSession,
        *,
        from_id: Optional[UUID] = None,
        to_id: Optional[UUID] = None,
    ) -> dict:
        """Recompute every hash in order and report the first break.

        Returns a dict with::

            {
                "valid": bool,
                "total_events": int,
                "broken_at": <uuid|None>,
                "last_hash": <hex|None>,
            }
        """
        stmt = select(AuditEvent).order_by(
            AuditEvent.timestamp.asc(), AuditEvent.id.asc()
        )
        if from_id is not None:
            stmt = stmt.where(AuditEvent.id >= from_id)
        if to_id is not None:
            stmt = stmt.where(AuditEvent.id <= to_id)

        result = await db.execute(stmt)
        rows = result.scalars().all()

        expected_prev: str = GENESIS_ROW_HASH
        total = 0
        last_hash: Optional[str] = None
        for row in rows:
            total += 1
            if row.event_type == "audit.genesis":
                # Genesis row has fixed values pinned by the migration.
                if (
                    row.prev_hash != GENESIS_PREV_HASH
                    or row.row_hash != GENESIS_ROW_HASH
                ):
                    return {
                        "valid": False,
                        "total_events": total,
                        "broken_at": str(row.id),
                        "last_hash": last_hash,
                    }
                expected_prev = row.row_hash
                last_hash = row.row_hash
                continue

            if row.prev_hash != expected_prev:
                return {
                    "valid": False,
                    "total_events": total,
                    "broken_at": str(row.id),
                    "last_hash": last_hash,
                }
            canonical_body = {
                "id": str(row.id),
                "timestamp": row.timestamp.isoformat(),
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "actor_ip": row.actor_ip,
                "actor_user_agent": row.actor_user_agent,
                "event_type": row.event_type,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "classification": row.classification,
                "org_id": str(row.org_id) if row.org_id else None,
                "outcome": row.outcome,
                "metadata_json": row.metadata_json or None,
            }
            recomputed = _compute_hash(row.prev_hash, canonical_body)
            if recomputed != row.row_hash:
                return {
                    "valid": False,
                    "total_events": total,
                    "broken_at": str(row.id),
                    "last_hash": last_hash,
                }
            expected_prev = row.row_hash
            last_hash = row.row_hash

        return {
            "valid": True,
            "total_events": total,
            "broken_at": None,
            "last_hash": last_hash,
        }


# Module-level singleton. Stateless — safe to share.
audit_service = AuditService()


__all__ = ["AuditService", "audit_service"]
