from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from app.db.models.persistence import Alert
from app.db.session import get_db
from app.core.security import require_clearance

router = APIRouter()

@router.get("/")
async def list_alerts(
    severity: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("RESTRICTED")),
):
    """
    List recent security alerts and anomalies.
    """
    query = select(Alert).order_by(desc(Alert.id))
    if severity:
        query = query.where(Alert.severity == severity.upper())
    
    result = await db.execute(query.limit(limit))
    return result.scalars().all()

@router.post("/{alert_id}/validate")
async def validate_alert(
    alert_id: str,
    validated_by: str = Query(...),
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("CONFIDENTIAL")),
):
    """
    Human-in-the-loop validation for critical alerts.
    """
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalars().first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
        
    alert.human_validated = True
    alert.validated_by = validated_by
    # alert.validation_ts = datetime.datetime.utcnow()
    
    await db.commit()
    return {"status": "validated", "alert_id": alert_id}
