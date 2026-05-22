from fastapi import APIRouter
router = APIRouter()

@router.get("/nodes")
async def get_mesh_nodes():
    return {"nodes": []}

@router.post("/broadcast")
async def broadcast_message(data: dict):
    return {"status": "broadcasted", "nodes_reached": 0}
