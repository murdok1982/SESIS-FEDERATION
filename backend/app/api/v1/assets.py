from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel, Field
from app.db.session import get_db

router = APIRouter()


class AssetRegisterIn(BaseModel):
    """Allowed-fields-only model para evitar mass-assignment."""
    id: str = Field(..., max_length=128)
    kind: str = Field(..., max_length=64)
    classification_level: str = Field(..., max_length=32, pattern=r"^(OPEN|RESTRICTED|CONFIDENTIAL|SECRET|TOP_SECRET)$")
    metadata: dict = Field(default_factory=dict)
    location: Optional[List[float]] = None  # Reservado: [lon, lat]; el server decide cómo persistirlo.


@router.post("/register")
async def register_asset(
    payload: AssetRegisterIn,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("RESTRICTED")),
):
    """
    Register a new asset in the system.
    Sólo se aceptan campos del modelo Pydantic; current_status/last_heartbeat/created_at los pone el servidor.
    """
    new_asset = Asset(
        id=payload.id,
        kind=payload.kind,
        classification_level=payload.classification_level,
        metadata_json=payload.metadata,
        current_status="registered"
    )
    db.add(new_asset)
    await db.commit()
    return {"status": "registered", "asset_id": new_asset.id}

@router.get("/{id}")
async def get_asset(
    id: str,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("RESTRICTED")),
):
    """
    Get current state of an asset.
    """
    result = await db.execute(select(Asset).where(Asset.id == id))
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset

@router.get("/")
async def list_assets(
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require_clearance("RESTRICTED")),
):
    """
    List all registered assets.
    """
    result = await db.execute(select(Asset))
    return result.scalars().all()
