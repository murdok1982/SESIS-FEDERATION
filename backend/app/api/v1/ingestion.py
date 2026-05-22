from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Dict, Any
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db

router = APIRouter()
logger = logging.getLogger("sesis.ingest")

@router.post("/events/ingest")
async def ingest_event(
    event: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("RESTRICTED")),
):
    """
    Ingest a Universal Event Envelope (UEE) message.
    1. Verify Signature
    2. Persist to DB (PostGIS/TimescaleDB)
    3. Publish to Bus (Async)
    """
    
    if not SecurityService.verify_signature(event):
        raise HTTPException(status_code=403, detail="Invalid signature or schema violation")
    
    data_service = DataService(db)
    success = await data_service.process_event(event)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to persist event")
    
    # Append-only Audit
    await data_service.log_audit(
        actor=event["asset_id"],
        action="INGEST_EVENT",
        resource_type="EVENT",
        resource_id=event["event_id"],
        context={"event_type": event["event_type"]}
    )
    
    logger.info(f"Event ingested, persisted and audited: {event['event_id']}")
    
    return {
        "status": "accepted",
        "event_id": event["event_id"],
        "received_at": event["ts"]
    }
