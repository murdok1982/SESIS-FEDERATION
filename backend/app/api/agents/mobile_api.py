from fastapi import APIRouter
router = APIRouter()

@router.get("/devices")
async def get_registered_devices():
    return {"devices": []}

@router.post("/wipe/{device_id}")
async def remote_wipe(device_id: str):
    return {"status": "wipe_initiated", "device_id": device_id}
