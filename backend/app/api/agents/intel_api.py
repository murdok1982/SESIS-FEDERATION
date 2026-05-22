from fastapi import APIRouter, Depends
router = APIRouter()

@router.get("/reports")
async def get_intel_reports():
    return {"reports": []}

@router.post("/reports")
async def create_intel_report(data: dict):
    return {"status": "created", "id": "report-001"}
