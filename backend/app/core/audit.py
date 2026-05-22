# -*- coding: utf-8 -*-
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class AuditChain:
    """Immutable audit chain with SHA-256 hash chaining."""

    def __init__(self):
        self.last_hash: Optional[str] = None

    async def record(
        self,
        event: str,
        actor: str,
        resource: str,
        classification: str = "restricted",
        details: Optional[Dict[str, Any]] = None,
        db_session=None,
    ) -> Dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "actor": actor,
            "resource": resource,
            "classification": classification,
            "details": details or {},
            "previous_hash": self.last_hash or "0000000000000000000000000000000000000000000000000000000000000000",
        }
        entry["hash"] = self._compute_hash(entry)

        if self.last_hash and entry["previous_hash"] != self.last_hash:
            logger.error(f"Audit chain integrity violation at {entry['timestamp']}")
            raise ValueError("Audit chain integrity violated: previous hash mismatch")

        self.last_hash = entry["hash"]

        if db_session:
            from app.db.models.audit import AuditLog
            log = AuditLog(**entry)
            db_session.add(log)
            await db_session.commit()

        logger.info(f"Audit: {event} by {actor} on {resource} [{classification}]")
        return entry

    def _compute_hash(self, entry: Dict) -> str:
        raw = json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(raw).hexdigest()

    def verify_chain(self, entries: list) -> bool:
        prev = None
        for entry in entries:
            expected_prev = prev or "0000000000000000000000000000000000000000000000000000000000000000"
            if entry["previous_hash"] != expected_prev:
                return False
            computed = self._compute_hash(
                {k: v for k, v in entry.items() if k != "hash"}
            )
            if entry["hash"] != computed:
                return False
            prev = entry["hash"]
        return True


audit_chain = AuditChain()
