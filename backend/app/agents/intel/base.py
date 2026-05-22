"""
Base classes shared by every intelligence agent.

Every concrete agent (OSINT, Synthesis, Scenario, ...) MUST inherit
from :class:`BaseAgent` and declare a ``max_classification``. The
base class enforces that any incoming :class:`AgentTask` does not
exceed the agent's clearance ceiling.

Agents that need an LLM MUST go through ``llm_router.generate`` —
direct calls to provider implementations are forbidden because they
would bypass the sovereignty gate.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from app.core.classification import (
    ClassificationLevel,
    TLP,
)
from app.services.intel.llm.exceptions import ClassificationViolationError


@dataclass
class AgentTask:
    """Generic agent invocation envelope.

    Attributes:
        kind: Short identifier (``osint_scan``, ``synthesis``, ...).
        classification: Sensitivity ceiling of the data the agent
            will see and produce.
        tlp: Sharing caveat that propagates with downstream outputs.
        user_id: Optional caller identifier (for audit, never logged
            alongside content).
        payload: Free-form structured input.
    """

    kind: str
    classification: ClassificationLevel = ClassificationLevel.PUBLIC
    tlp: TLP = TLPMarker.CLEAR
    user_id: Optional[UUID] = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Generic agent output envelope."""

    kind: str
    classification: ClassificationLevel
    tlp: TLP
    content: Any
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract intelligence agent."""

    name: str = "unknown-agent"
    max_classification: ClassificationLevel = ClassificationLevel.PUBLIC

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, task: AgentTask) -> AgentResult:
        """Validate then dispatch to :meth:`execute`."""
        self.validate_classification(task)
        return await self.execute(task)

    @abstractmethod
    async def execute(self, task: AgentTask) -> AgentResult:  # pragma: no cover
        """Concrete implementation."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def validate_classification(self, task: AgentTask) -> None:
        cls = ClassificationLevel(task.classification)
        if cls > self.max_classification:
            raise ClassificationViolationError(
                f"Agent {self.name!r} max_classification="
                f"{self.max_classification.name} cannot run task with "
                f"classification={cls.name}"
            )


__all__ = ["BaseAgent", "AgentTask", "AgentResult"]
