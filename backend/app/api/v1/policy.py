from fastapi import APIRouter, Body, Depends
from app.services.policy import PolicyEvaluator
from typing import Dict, Any
from app.core.security import require_clearance

router = APIRouter()

@router.post("/evaluate")
async def evaluate_policy(
    input_data: Dict[str, Any] = Body(...),
    principal: dict = Depends(require_clearance("CONFIDENTIAL")),
):
    """
    Evaluate an ABAC policy request.
    Inputs: subject, resource, context
    """
    subject = input_data.get("subject", {})
    resource = input_data.get("resource", {})
    context = input_data.get("context", {})
    
    result = PolicyEvaluator.evaluate(subject, resource, context)
    return result
