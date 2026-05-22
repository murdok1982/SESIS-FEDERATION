from fastapi import APIRouter, Depends
from app.core.security import get_current_user

router = APIRouter()

@router.get("/status")
async def agent_system_status(user: dict = Depends(get_current_user)):
    return {"module": "agents", "status": "operational", "source": "SpyManager"}
