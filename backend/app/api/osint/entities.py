from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.osint.deps import *
from app.db.models.osint.case import Case
from app.db.models.osint.entity import Entity
from app.db.models.osint.entity import EntityCreate, EntityMergeRequest, EntityResponse, EntityUpdate

router = APIRouter()

async def _assert_case_access(db: AsyncSession, case_id: str, user) -> Case:
    case = (
        await db.execute(select(Case).where(Case.id == case_id, Case.deleted.is_(False)))
    ).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    assert_resource_access(
        user,
        owner_id=case.operator_id,
        classification=getattr(case, "classification", "UNCLASSIFIED"),
    )
    return case

@router.get("", response_model=list[EntityResponse])
async def list_entities(
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:cases"))],
    case_id: str | None = None,
    entity_type: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[EntityResponse]:
    if case_id:
        await _assert_case_access(db, case_id, user)

    q = (
        select(Entity)
        .join(Case, Case.id == Entity.case_id)
        .where(Entity.merged_into_id.is_(None), Case.deleted.is_(False))
    )
    is_admin = getattr(user, "is_superuser", False) or "admin" in (
        getattr(user, "scopes", []) or []
    )
    if not is_admin:
        q = q.where(Case.operator_id == user.id)  # type: ignore[attr-defined]
    if case_id:
        q = q.where(Entity.case_id == case_id)
    if entity_type:
        q = q.where(Entity.entity_type == entity_type)
    q = q.order_by(Entity.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return [EntityResponse.model_validate(e) for e in result.scalars().all()]

@router.post("", response_model=EntityResponse, status_code=status.HTTP_201_CREATED)
async def create_entity(
    body: EntityCreate,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("write:cases"))],
) -> EntityResponse:
    await _assert_case_access(db, body.case_id, user)
    entity = Entity(**body.model_dump())
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return EntityResponse.model_validate(entity)

@router.get("/{entity_id}", response_model=EntityResponse)
async def get_entity(
    entity_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:cases"))],
) -> EntityResponse:
    entity = await _get_or_404(db, entity_id, user)
    return EntityResponse.model_validate(entity)

@router.put("/{entity_id}", response_model=EntityResponse)
async def update_entity(
    entity_id: str,
    body: EntityUpdate,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("write:cases"))],
) -> EntityResponse:
    entity = await _get_or_404(db, entity_id, user)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(entity, field, value)
    await db.commit()
    await db.refresh(entity)
    return EntityResponse.model_validate(entity)

@router.post("/{entity_id}/merge", status_code=status.HTTP_204_NO_CONTENT)
async def merge_entity(
    entity_id: str,
    body: EntityMergeRequest,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("write:cases"))],
) -> None:
    entity = await _get_or_404(db, entity_id, user)
    target = await _get_or_404(db, body.target_entity_id, user)
    if entity.case_id != target.case_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Entities must be in the same case")
    entity.merged_into_id = target.id
    await db.commit()

@router.get("/graph/{case_id}")
async def get_entity_graph(
    case_id: str,
    db: DBSession,
    user: Annotated[object, Depends(require_scope("read:cases"))],
) -> dict:
    await _assert_case_access(db, case_id, user)
    result = await db.execute(select(Entity).where(Entity.case_id == case_id))
    entities = result.scalars().all()
    nodes = [
        {
            "id": e.id,
            "label": e.display_name or e.value,
            "type": e.entity_type,
            "value": e.value,
            "confidence": e.confidence_score,
            "is_target": e.is_target,
        }
        for e in entities
    ]
    edges = [
        {"source": e.id, "target": e.merged_into_id, "type": "merged_into"}
        for e in entities
        if e.merged_into_id
    ]
    return {"nodes": nodes, "edges": edges}

async def _get_or_404(db: AsyncSession, entity_id: str, user) -> Entity:
    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    await _assert_case_access(db, entity.case_id, user)
    return entity
