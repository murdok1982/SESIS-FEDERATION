from fastapi import APIRouter
from app.services.tactical.psyops import psyops

router = APIRouter()

@router.post("/message")
async def generate_psyops_message(target_audience: str, objective: str, context: dict = None):
    return {"message": await psyops.generate_message(target_audience, objective, context)}

@router.post("/campaign")
async def plan_campaign(campaign_params: dict):
    return await psyops.plan_campaign(campaign_params)

@router.post("/deception")
async def generate_deception(operation_params: dict):
    return await psyops.generate_deception_plan(operation_params)
