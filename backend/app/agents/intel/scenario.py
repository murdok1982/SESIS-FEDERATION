"""
Scenario Agent — bounded ``what-if`` projections over a fixed brief.

The agent is intentionally restricted to the context of a single
report. It must not pull external world knowledge into its
projections — that is enforced via the system prompt AND by the
classification ceiling: a SECRET scenario will only run against a
local LLM.
"""

from __future__ import annotations

from typing import Any

from app.agents.intel.base import AgentResult, AgentTask, BaseAgent
from app.core.classification import ClassificationLevel, TLPMarker as TLP
from app.services.llm import LLMTask, llm_router


_SCENARIO_SYSTEM_PROMPT = (
    "You are a restricted Scenario Simulator. You may ONLY use the "
    "context of the provided report to project outcomes. DO NOT "
    "introduce external world knowledge. Where information is "
    "missing, state so explicitly."
)

_INTAKE_SYSTEM_PROMPT = (
    "You are an Intake Operative. Maintain a professional, sterile, "
    "deeply psychological tone. Extract Country, Category, and Entities. "
    "Only ask for phone number if the contributor opts to be verified."
)


class ScenarioAgent(BaseAgent):
    """Projects bounded alternative outcomes for an existing brief."""

    name = "Scenario-Sigma"
    max_classification = ClassificationLevel.SECRET

    async def execute(self, task: AgentTask) -> AgentResult:
        report_md: str = task.payload.get("report_markdown") or ""
        variable: str = task.payload.get("variable") or ""
        prompt = (
            f"REPORT CONTEXT:\n{report_md}\n\n"
            f"USER VARIABLE:\n{variable}\n\n"
            "Calculate the risk trajectory bounded by the report."
        )
        llm_task = LLMTask(
            prompt=prompt,
            system_prompt=_SCENARIO_SYSTEM_PROMPT,
            classification=task.classification,
            metadata={"agent": self.name},
        )
        result = await llm_router.generate(llm_task)
        return AgentResult(
            kind="scenario_projection",
            classification=task.classification,
            tlp=task.tlp,
            content=result.text,
            metadata={
                "provider": result.provider,
                "model": result.model,
                "latency_ms": result.latency_ms,
            },
        )

    # Backwards-compatible shim
    async def simulate_what_if(
        self,
        existing_report_markdown: str,
        user_variable: str,
        *,
        classification: ClassificationLevel = ClassificationLevel.PUBLIC,
        tlp: TLP = TLP.CLEAR,
    ) -> str:
        task = AgentTask(
            kind="scenario",
            classification=classification,
            tlp=tlp,
            payload={
                "report_markdown": existing_report_markdown,
                "variable": user_variable,
            },
        )
        result = await self.run(task)
        return str(result.content or "")


class ContributorIntakeAgent(BaseAgent):
    """Chatbot agent that structures voluntary public signals.

    Operates exclusively on PUBLIC data (contributor narratives that
    the contributor themselves chose to share).
    """

    name = "Intake-Iota"
    max_classification = ClassificationLevel.PUBLIC

    async def execute(self, task: AgentTask) -> AgentResult:
        user_message: str = task.payload.get("user_message") or ""
        chat_history: Any = task.payload.get("chat_history") or []
        prompt = f"History: {chat_history}\nUser: {user_message}\nRespond:"
        llm_task = LLMTask(
            prompt=prompt,
            system_prompt=_INTAKE_SYSTEM_PROMPT,
            classification=ClassificationLevel.PUBLIC,
            metadata={"agent": self.name},
        )
        result = await llm_router.generate(llm_task)
        return AgentResult(
            kind="intake_reply",
            classification=ClassificationLevel.PUBLIC,
            tlp=TLP.CLEAR,
            content=result.text,
            metadata={"provider": result.provider, "model": result.model},
        )

    # Backwards-compatible shim
    async def process_intake(self, user_message: str, chat_history: list) -> str:
        task = AgentTask(
            kind="contributor_intake",
            classification=ClassificationLevel.PUBLIC,
            tlp=TLP.CLEAR,
            payload={"user_message": user_message, "chat_history": chat_history},
        )
        result = await self.run(task)
        return str(result.content or "")


scenario_agent = ScenarioAgent()
contributor_intake_agent = ContributorIntakeAgent()


__all__ = [
    "ScenarioAgent",
    "ContributorIntakeAgent",
    "scenario_agent",
    "contributor_intake_agent",
]
