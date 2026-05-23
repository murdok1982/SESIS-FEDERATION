from fastapi import APIRouter
from app.services.tactical.joint_fires import jf_coord

router = APIRouter()

@router.post("/deconflict")
async def deconflict(fire_mission: dict, active_fires: list):
    return await jf_coord.deconflict(fire_mission, active_fires)

@router.post("/coordinate")
async def coordinate(fire_plan: dict):
    return await jf_coord.coordinate(fire_plan)

@router.post("/assess")
async def assess_collateral(target: dict, weapon: dict):
    return await jf_coord.assess_collateral(target, weapon)
