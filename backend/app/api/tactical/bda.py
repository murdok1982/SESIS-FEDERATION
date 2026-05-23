from fastapi import APIRouter
from app.services.tactical.bda import bda

router = APIRouter()

@router.post("/assess")
async def assess_bda(strike_data: dict):
    return await bda.assess(strike_data)

@router.post("/satellite")
async def satellite_bda(pre_image: str, post_image: str):
    return await bda.satellite_bda(pre_image, post_image)

@router.post("/consolidated")
async def consolidated_bda(sources: list):
    return await bda.consolidated_bda(sources)
