from fastapi import APIRouter
router = APIRouter()

@router.post("/transcribe")
async def transcribe_audio(data: dict):
    return {"transcript": ""}
