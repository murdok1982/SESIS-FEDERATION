"""
OpenClaw Orchestrator — top-level coordinator.

The orchestrator does not call LLMs directly. It builds typed
:class:`AgentTask` envelopes and dispatches them to the relevant
sub-agent. Every dispatch method requires an explicit
``classification`` argument — there is no implicit default. Calling
with ``classification=None`` is rejected.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional
from uuid import UUID

from app.agents.intel.base import AgentResult, AgentTask
from app.agents.intel.osint import OSINTAgent
from app.agents.intel.scenario import ScenarioAgent
from app.agents.intel.synthesis import SynthesisAgent
from app.core.classification import ClassificationLevel, TLPMarker as TLP

logger = logging.getLogger(__name__)


class OpenClawOrchestrator:
    """Top-level agent coordinator."""

    def __init__(self) -> None:
        self.name = "OpenClaw-Prime"
        self._osint = OSINTAgent()
        self._synthesis = SynthesisAgent()
        self._scenario = ScenarioAgent()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _require_classification(
        classification: Optional[ClassificationLevel],
    ) -> ClassificationLevel:
        if classification is None:
            raise ValueError(
                "Orchestrator dispatch requires an explicit classification. "
                "Pass ClassificationLevel.PUBLIC for open-source workloads."
            )
        return ClassificationLevel.from_any(classification)

    # ------------------------------------------------------------------
    # Public dispatch methods
    # ------------------------------------------------------------------

    async def dispatch_osint_scan(
        self,
        target_country: str,
        *,
        classification: Optional[ClassificationLevel] = None,
        tlp: TLP = TLP.CLEAR,
        user_id: Optional[UUID] = None,
    ) -> AgentResult:
        cls = self._require_classification(classification)
        logger.info(
            "orchestrator.dispatch_osint target=%s classification=%s",
            target_country,
            cls.name,
        )
        task = AgentTask(
            kind="osint_scan",
            classification=cls,
            tlp=tlp,
            user_id=user_id,
            payload={"country_iso": target_country.upper()},
        )
        return await self._osint.run(task)

    async def dispatch_synthesis(
        self,
        raw_events: Iterable[Any],
        topic: str,
        *,
        classification: Optional[ClassificationLevel] = None,
        tlp: TLP = TLP.CLEAR,
        user_id: Optional[UUID] = None,
    ) -> str:
        cls = self._require_classification(classification)
        logger.info(
            "orchestrator.dispatch_synthesis topic=%r classification=%s",
            topic,
            cls.name,
        )
        task = AgentTask(
            kind="synthesis",
            classification=cls,
            tlp=tlp,
            user_id=user_id,
            payload={"country": topic, "signals": list(raw_events)},
        )
        result = await self._synthesis.run(task)
        return str(result.content or "")

    async def process_user_scenario(
        self,
        report_context: str,
        user_variable: str,
        *,
        classification: Optional[ClassificationLevel] = None,
        tlp: TLP = TLP.CLEAR,
        user_id: Optional[UUID] = None,
    ) -> str:
        cls = self._require_classification(classification)
        logger.info(
            "orchestrator.process_user_scenario classification=%s",
            cls.name,
        )
        task = AgentTask(
            kind="scenario",
            classification=cls,
            tlp=tlp,
            user_id=user_id,
            payload={
                "report_markdown": report_context,
                "variable": user_variable,
            },
        )
        result = await self._scenario.run(task)
        return str(result.content or "")


openclaw_master = OpenClawOrchestrator()


__all__ = ["OpenClawOrchestrator", "openclaw_master"]
