import uuid
from fastapi import APIRouter, Request

from app.core.limiter import limiter
from app.agents.intel.scenario import ContributorIntakeAgent
from app.schemas.contributor import ContributorIntakeRequest, ContributorIntakeResponse

router = APIRouter()

_intake_agent = ContributorIntakeAgent()


@router.post("/intake", response_model=ContributorIntakeResponse)
@limiter.limit("10/minute")
async def contributor_intake(
    request: Request,  # required by slowapi for IP-based rate limiting
    body: ContributorIntakeRequest,
) -> ContributorIntakeResponse:
    session_id = body.session_id or str(uuid.uuid4())
    response_text = await _intake_agent.process_intake(
        user_message=body.message,
        chat_history=[],
    )
    return ContributorIntakeResponse(response=response_text, session_id=session_id)
