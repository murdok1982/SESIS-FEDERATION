from fastapi import APIRouter
router = APIRouter()

@router.get("/wearables")
async def get_wearable_devices():
    return {"wearables": []}

@router.post("/wearables/alert")
async def wearable_alert(data: dict):
    return {"status": "alert_sent"}
