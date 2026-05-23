from fastapi import APIRouter
from app.services.agents.sensor_mesh import sensor_mesh

router = APIRouter()

@router.post("/register")
async def register_sensor(sensor_id: str, sensor_type: str, location: dict):
    return await sensor_mesh.register_sensor(sensor_id, sensor_type, location)

@router.post("/ingest")
async def ingest_reading(sensor_id: str, reading: dict):
    return await sensor_mesh.ingest_reading(sensor_id, reading)

@router.get("/status")
async def mesh_status():
    return await sensor_mesh.get_mesh_status()
