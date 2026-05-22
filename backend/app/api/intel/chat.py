import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.intel.deps import get_db, get_current_active_user
from app.db.models.intel.interactions import (
    ChatSession as ChatSessionModel,
    ChatMessage as ChatMessageModel,
    ScenarioRun,
)
from app.db.models.intel.reports import DailyReport
from app.db.models.intel.user import User
from app.schemas.chat import (
    ChatSession,
    ChatSessionCreate,
    ChatMessage,
    ChatMessageCreate,
    ChatResponse,
    ScenarioRequest,
    ScenarioResponse,
)
from app.agents.intel.orchestrator import openclaw_master
from app.core.classification import ClassificationLevel, TLPMarker

router = APIRouter()


@router.post("/sessions", response_model=ChatSession, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ChatSession:
    report_result = await db.execute(
        select(DailyReport).where(DailyReport.id == body.report_id)
    )
    if not report_result.scalars().first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    session = ChatSessionModel(
        user_id=current_user.id,
        report_bind_id=body.report_id,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return ChatSession.model_validate(session)


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessage])
async def get_messages(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ChatMessage]:
    session_result = await db.execute(
        select(ChatSessionModel).where(
            ChatSessionModel.id == session_id,
            ChatSessionModel.user_id == current_user.id,
        )
    )
    if not session_result.scalars().first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    result = await db.execute(
        select(ChatMessageModel)
        .where(ChatMessageModel.session_id == session_id)
        .order_by(ChatMessageModel.created_at)
    )
    messages = result.scalars().all()
    return [ChatMessage.model_validate(m) for m in messages]


@router.post("/sessions/{session_id}/message", response_model=ChatResponse)
async def send_message(
    session_id: uuid.UUID,
    body: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ChatResponse:
    session_result = await db.execute(
        select(ChatSessionModel).where(
            ChatSessionModel.id == session_id,
            ChatSessionModel.user_id == current_user.id,
        )
    )
    session = session_result.scalars().first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Fetch the bound report for RAG context
    report_result = await db.execute(
        select(DailyReport).where(DailyReport.id == session.report_bind_id)
    )
    report = report_result.scalars().first()
    report_context = report.content_json if report else ""

    # Persist user message
    user_msg = ChatMessageModel(
        session_id=session_id,
        role="user",
        content=body.content,
    )
    db.add(user_msg)
    await db.flush()

    # Generate agent response (bounded to report context). The
    # classification of the report drives the LLM routing.
    report_cls = ClassificationLevel(
        int(getattr(report, "classification", ClassificationLevel.PUBLIC))
    )
    agent_text = await openclaw_master.dispatch_synthesis(
        raw_events=[body.content],
        topic=report_context[:500] if report_context else body.content,
        classification=report_cls,
        user_id=current_user.id,
    )

    assistant_msg = ChatMessageModel(
        session_id=session_id,
        role="assistant",
        content=agent_text,
    )
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)

    return ChatResponse(
        message=ChatMessage.model_validate(user_msg),
        response=agent_text,
    )


@router.post("/scenario", response_model=ScenarioResponse, status_code=status.HTTP_201_CREATED)
async def run_scenario(
    body: ScenarioRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ScenarioResponse:
    report_result = await db.execute(
        select(DailyReport).where(DailyReport.id == body.report_id)
    )
    report = report_result.scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    report_cls = ClassificationLevel(
        int(getattr(report, "classification", ClassificationLevel.PUBLIC))
    )
    output = await openclaw_master.process_user_scenario(
        report_context=report.content_json,
        user_variable=body.variable,
        classification=report_cls,
        user_id=current_user.id,
    )

    run = ScenarioRun(
        user_id=current_user.id,
        report_id=body.report_id,
        input_variables={"variable": body.variable},
        output_markdown=output,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    return ScenarioResponse(scenario_id=run.id, output=output)
