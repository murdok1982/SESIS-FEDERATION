from fastapi import APIRouter
router = APIRouter()

@router.post("/encode")
async def stego_encode(data: dict):
    return {"status": "encoded"}

@router.post("/decode")
async def stego_decode(data: dict):
    return {"message": ""}
