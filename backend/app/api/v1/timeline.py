from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from app.db.models.persistence import Telemetry
from app.db.session import get_db
from app.core.security import require_clearance

router = APIRouter()

@router.get("/query")
async def query_timeline(
    asset_id: str,
    parameter: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("RESTRICTED")),
):
    """
    Query time-series telemetry data for a specific asset.
    Leverages TimescaleDB hypertables.
    """
    query = select(Telemetry).where(Telemetry.asset_id == asset_id).order_by(desc(Telemetry.ts))
    if parameter:
        query = query.where(Telemetry.parameter == parameter)
        
    result = await db.execute(query.limit(limit))
    return result.scalars().all()
