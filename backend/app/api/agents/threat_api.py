from fastapi import APIRouter
router = APIRouter()

@router.get("/predictions")
async def get_threat_predictions():
    return {"predictions": []}
