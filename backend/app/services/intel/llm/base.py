"""
Abstract LLM provider contract.

Every concrete provider (Ollama, vLLM, OpenRouter, ...) must
subclass :class:`LLMProvider` and implement ``_generate``. The base
class enforces the classification gate before any network call is
made — concrete providers should NOT bypass it.

Design rules:
    * Providers are stateless except for configuration.
    * Providers MUST advertise ``forbidden_for_classified`` honestly.
    * Providers MUST NOT log prompt or completion content. Only
      metadata (token counts, model id, latency, classification).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.core.classification import ClassificationLevel, TLPMarker
from app.services.intel.llm.exceptions import ClassificationViolationError


@dataclass
class LLMTask:
    """A single LLM invocation.

    Attributes:
        prompt: User-level instruction.
        system_prompt: Optional system / role instruction.
        classification: Sensitivity level of the *content* being processed.
            Used by the router to pick a compliant provider.
        model: Optional model hint. Providers may ignore it.
        temperature: Sampling temperature (defaults to 0.2 for
            deterministic intelligence output).
        max_tokens: Optional cap on completion tokens.
        metadata: Free-form provenance bag (request id, agent name,
            user id hash, ...). Never logged with the prompt itself.
    """

    prompt: str
    system_prompt: str = "You are an intelligence operative."
    classification: ClassificationLevel = ClassificationLevel.PUBLIC
    model: Optional[str] = None
    temperature: float = 0.2
    max_tokens: Optional[int] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class LLMResult:
    """Provider response wrapped with provenance for auditing."""

    text: str
    provider: str
    model: str
    classification: ClassificationLevel
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[int] = None


class LLMProvider(ABC):
    """Abstract base class for every LLM backend.

    Subclasses MUST set:
        * ``name``: short identifier used in logs and metrics.
        * ``forbidden_for_classified``: True for any provider that
          sends data to infrastructure outside the operator's
          sovereign control (e.g. external SaaS APIs).
    """

    name: str = "unknown"
    forbidden_for_classified: bool = True
    # Maximum classification this provider can handle. Defaults to the
    # most permissive — concrete providers should narrow it.
    max_classification: ClassificationLevel = ClassificationLevel.SECRET

    async def is_available(self) -> bool:
        """Return True if the provider can serve traffic right now.

        Default implementation returns True. Concrete providers should
        ping their backend (with a tight timeout) and cache the result
        for a short window if needed.
        """
        return True

    async def generate(self, task: LLMTask) -> LLMResult:
        """Validate classification and dispatch to ``_generate``.

        Raises:
            ClassificationViolationError: if the task's classification
                exceeds what this provider may handle.
        """
        self._enforce_classification(task)
        return await self._generate(task)

    @abstractmethod
    async def _generate(self, task: LLMTask) -> LLMResult:  # pragma: no cover - abstract
        """Concrete provider call. Must not log prompt content."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _enforce_classification(self, task: LLMTask) -> None:
        cls = ClassificationLevel(task.classification)
        if cls > self.max_classification:
            raise ClassificationViolationError(
                f"Provider {self.name!r} max_classification="
                f"{self.max_classification.name} cannot serve task with "
                f"classification={cls.name}"
            )
        if self.forbidden_for_classified and cls > ClassificationLevel.PUBLIC:
            raise ClassificationViolationError(
                f"Provider {self.name!r} is marked forbidden_for_classified=True "
                f"and cannot serve task with classification={cls.name}"
            )


__all__ = ["LLMProvider", "LLMTask", "LLMResult"]
