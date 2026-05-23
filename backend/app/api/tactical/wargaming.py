from fastapi import APIRouter
from app.services.tactical.wargaming import wargaming

router = APIRouter()

@router.post("/simulate")
async def simulate_coa(coa: dict, scenario: dict):
    return await wargaming.simulate_coa(coa, scenario)

@router.post("/compare")
async def compare_coas(coas: list, scenario: dict):
    return await wargaming.compare_coas(coas, scenario)

@router.post("/montecarlo")
async def monte_carlo(coa: dict, iterations: int = 1000):
    return await wargaming.monte_carlo(coa, iterations)
