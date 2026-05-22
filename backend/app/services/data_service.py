from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db.models.persistence import Asset, Event, Telemetry, AuditLog
from typing import Dict, Any
import datetime
import hashlib
import json
import logging

logger = logging.getLogger("sesis.services.data")

class DataService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_audit(self, actor: str, action: str, resource_type: str, resource_id: str, context: Dict[str, Any] = {}):
        """
        Record an entry in the append-only audit log con hash chain (CRITICAL-4).
        """
        try:
            # Encadenar con la fila previa.
            prev_q = await self.db.execute(
                select(AuditLog.row_hash).order_by(AuditLog.id.desc()).limit(1)
            )
            prev_hash = prev_q.scalar() or ("0" * 64)

            ts = datetime.datetime.utcnow()
            canonical = json.dumps(
                {
                    "actor": actor,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "context": context,
                    "ts": ts.isoformat(),
                },
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            row_hash = hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()

            new_log = AuditLog(
                ts=ts,
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                context=context,
                prev_hash=prev_hash,
                row_hash=row_hash,
            )
            self.db.add(new_log)
            # await self.db.commit() # Usually called by the caller or specialized commit
        except Exception as e:
            logger.error(f"Audit Logging Failed: {e}")

    async def process_event(self, event_data: Dict[str, Any]):
        """
        Persists a UEE event into the database.
        Splits logic based on event_type.
        """
        try:
            # 1. Store the raw event
            new_event = Event(
                event_id=event_data["event_id"],
                event_type=event_data["event_type"],
                asset_id=event_data["asset_id"],
                ts=event_data["ts"],
                geo_point=f"POINT({event_data['geo']['lon']} {event_data['geo']['lat']})",
                classification_level=event_data["classification_level"],
                confidence_score=event_data["confidence_score"],
                payload=event_data["payload"],
                signature=event_data["signature"]
            )
            self.db.add(new_event)
            
            # 2. Update Asset state for heartbeats and status changes
            if event_data["event_type"] in ["asset_heartbeat", "asset_status_change"]:
                await self.update_asset_state(event_data)
                
            # 3. Handle telemetry
            if event_data["event_type"] == "vehicle_telemetry_sample":
                await self.store_telemetry(event_data)
                
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error processing event: {e}")
            return False

    async def update_asset_state(self, event_data: Dict[str, Any]):
        asset_id = event_data["asset_id"]
        # In a real app, we'd upsert. For now, simple update logic.
        q = update(Asset).where(Asset.id == asset_id).values(
            last_heartbeat=event_data["ts"],
            location=f"POINT({event_data['geo']['lon']} {event_data['geo']['lat']})",
            current_status=event_data["payload"].get("status", "active")
        )
        await self.db.execute(q)

    async def store_telemetry(self, event_data: Dict[str, Any]):
        payload = event_data["payload"]
        new_telemetry = Telemetry(
            ts=event_data["ts"],
            asset_id=event_data["asset_id"],
            parameter=payload.get("parameter", "unknown"),
            value=payload.get("value", 0.0),
            unit=payload.get("unit"),
            metadata_json=payload.get("metadata", {})
        )
        self.db.add(new_telemetry)
