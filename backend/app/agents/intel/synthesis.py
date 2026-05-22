"""
Synthesis Agent — turns raw intelligence signals into a structured brief.

Routes every LLM call through :data:`llm_router`, which enforces the
sovereignty gate: any task with ``classification >= CONFIDENTIAL``
will be served by a local provider (Ollama / vLLM) only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.intel.base import AgentResult, AgentTask, BaseAgent
from app.core.classification import ClassificationLevel, TLPMarker as TLP
from app.services.llm import LLMTask, llm_router


_SYSTEM_PROMPT = (
    "You are an elite intelligence synthesis operative. Use markdown, "
    "formal tone, extreme precision. Do not invent sources. Cite only "
    "the signals provided. Mark uncertainty explicitly."
)


class SynthesisAgent(BaseAgent):
    """Compose an executive brief from a list of signals."""

    name = "Synthesis-Prime"
    max_classification = ClassificationLevel.SECRET

    async def execute(self, task: AgentTask) -> AgentResult:
        country: str = task.payload.get("country") or "UNKNOWN"
        signals: List[Dict[str, Any]] = task.payload.get("signals") or []
        prompt = (
            f"Synthesize these intelligence signals for {country} into a "
            f"unified Executive Brief.\n\nSignals: {signals}"
        )
        llm_task = LLMTask(
            prompt=prompt,
            system_prompt=_SYSTEM_PROMPT,
            classification=task.classification,
            metadata={"agent": self.name, "country": country},
        )
        result = await llm_router.generate(llm_task)
        return AgentResult(
            kind="synthesis_brief",
            classification=task.classification,
            tlp=task.tlp,
            content=result.text,
            metadata={
                "provider": result.provider,
                "model": result.model,
                "latency_ms": result.latency_ms,
            },
        )

    # ------------------------------------------------------------------
    # Backwards-compatible shim
    # ------------------------------------------------------------------
    async def generate_daily_report(
        self,
        country: str,
        signals: List[Dict[str, Any]],
        *,
        classification: ClassificationLevel = ClassificationLevel.PUBLIC,
        tlp: TLP = TLP.CLEAR,
    ) -> str:
        """Compatibility helper used by older endpoints.

        Note: callers MUST pass the data's classification explicitly
        once they are aware of it. The default PUBLIC preserves
        previous behaviour for legacy code paths but should be removed
        in favour of explicit propagation.
        """
        task = AgentTask(
            kind="synthesis",
            classification=classification,
            tlp=tlp,
            payload={"country": country, "signals": signals},
        )
        result = await self.run(task)
        return str(result.content or "")


synthesis_agent = SynthesisAgent()


__all__ = ["SynthesisAgent", "synthesis_agent"]
