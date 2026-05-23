from fastapi import APIRouter
from app.services.tactical.opord_generator import opord_gen

router = APIRouter()

@router.post("/generate")
async def generate_opord(mission_params: dict):
    return await opord_gen.generate(mission_params)

@router.post("/fragord")
async def generate_fragord(base_opord: dict, updates: dict):
    return await opord_gen.generate_fragmentary(base_opord, updates)

@router.get("/{opord_id}")
async def get_opord(opord_id: str):
    return {"id": opord_id, "status": "draft"}

@router.post("/{opord_id}/validate")
async def validate_opord(opord_id: str, opord: dict):
    return await opord_gen.validate(opord)
