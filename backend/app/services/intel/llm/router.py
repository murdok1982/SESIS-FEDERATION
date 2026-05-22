"""
LLM router — picks a provider that satisfies the task's classification.

Routing rules (hard, in order):
    1. If ``task.classification > PUBLIC``: only providers with
       ``forbidden_for_classified=False`` and
       ``max_classification >= task.classification`` are considered.
       External providers are NEVER used for classified data, even
       as fallback.
    2. If ``task.classification >= CONFIDENTIAL`` and ``STATE_GRADE_MODE``
       is enabled, the router refuses to use ANY external provider
       and fails closed when no local provider is reachable.
    3. For PUBLIC tasks: try Ollama first, then vLLM, and only then
       OpenRouter if ``ENABLE_OPENROUTER_FALLBACK=true``.

The router NEVER logs the prompt or the completion. It logs only
metadata: classification level, provider name, model id, latency,
token counts when known.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable

from app.core.classification import ClassificationLevel, TLPMarker
from app.core.config import settings
from app.services.intel.llm.base import LLMProvider, LLMResult, LLMTask
from app.services.intel.llm.exceptions import (
    AllProvidersFailed,
    ClassificationViolationError,
    ProviderUnavailable,
)
from app.services.intel.llm.providers.ollama import OllamaProvider
from app.services.intel.llm.providers.openrouter import OpenRouterProvider
from app.services.intel.llm.providers.vllm import VLLMProvider

logger = logging.getLogger(__name__)


async def _audit_dispatch(
    *,
    provider: str,
    classification: ClassificationLevel,
    outcome: str,
    metadata: dict,
) -> None:
    """Best-effort audit append for a router dispatch.

    Opens its own session so the audit row is durable even when the
    surrounding request transaction rolls back. Never raises — audit
    must not break inference availability.
    """
    try:
        from app.db.session import async_session
        from app.services.intel.audit import audit_service

        async with AsyncSessionLocal() as db:
            await audit_service.record(
                db,
                event_type="llm.dispatch",
                resource_type="llm_provider",
                resource_id=provider,
                classification=int(classification),
                outcome=outcome,
                metadata=metadata,
            )
            await db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("llm.router.audit_failed err=%r", exc)


class LLMRouter:
    """Sovereign-by-default router for LLM tasks."""

    def __init__(self, providers: Iterable[LLMProvider] | None = None) -> None:
        if providers is None:
            providers = self._default_chain()
        self._providers: list[LLMProvider] = list(providers)

    # ------------------------------------------------------------------
    # Default provider chain
    # ------------------------------------------------------------------

    @staticmethod
    def _default_chain() -> list[LLMProvider]:
        # Order = preference order. Local providers first, external last.
        chain: list[LLMProvider] = [OllamaProvider(), VLLMProvider()]
        # OpenRouter is appended even when disabled — is_available() will
        # filter it out at request time. Keeping it in the list makes the
        # decision explicit and auditable.
        chain.append(OpenRouterProvider())
        return chain

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def providers(self) -> tuple[LLMProvider, ...]:
        return tuple(self._providers)

    def _eligible(self, task: LLMTask) -> list[LLMProvider]:
        cls = ClassificationLevel(task.classification)
        out: list[LLMProvider] = []
        for p in self._providers:
            if p.max_classification < cls:
                continue
            if cls > ClassificationLevel.PUBLIC and p.forbidden_for_classified:
                continue
            out.append(p)
        return out

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def generate(self, task: LLMTask) -> LLMResult:
        """Run the task on the first compliant, reachable provider.

        Raises:
            ClassificationViolationError: if no provider is allowed to
                handle the task's classification at all.
            AllProvidersFailed: if every eligible provider is unreachable.
        """
        cls = ClassificationLevel(task.classification)
        eligible = self._eligible(task)

        if not eligible:
            raise ClassificationViolationError(
                f"No registered provider may handle classification={cls.name}. "
                "Configure a local provider (Ollama or vLLM)."
            )

        # State-grade hard rule: for CONFIDENTIAL+ refuse if no LOCAL provider
        # is in the eligible set — defensive check, also enforced by the
        # forbidden_for_classified filter above.
        if cls >= ClassificationLevel.CONFIDENTIAL and settings.STATE_GRADE_MODE:
            has_local = any(not p.forbidden_for_classified for p in eligible)
            if not has_local:
                raise ClassificationViolationError(
                    "STATE_GRADE_MODE=true: classification "
                    f"{cls.name} requires a local provider but none are "
                    "eligible. Refusing to proceed."
                )

        last_error: Exception | None = None
        for provider in eligible:
            try:
                available = await provider.is_available()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "llm.router.availability_check_failed provider=%s error=%s",
                    provider.name,
                    exc,
                )
                available = False

            if not available:
                logger.info(
                    "llm.router.skip provider=%s reason=unavailable "
                    "classification=%s",
                    provider.name,
                    cls.name,
                )
                continue

            if provider.forbidden_for_classified and cls == ClassificationLevel.PUBLIC:
                # PUBLIC + external: allowed only when fallback flag is on.
                if not settings.ENABLE_OPENROUTER_FALLBACK:
                    logger.info(
                        "llm.router.skip provider=%s reason=external_disabled",
                        provider.name,
                    )
                    continue
                logger.warning(
                    "llm.router.external_fallback provider=%s "
                    "classification=PUBLIC — data will leave sovereign perimeter",
                    provider.name,
                )

            started = time.monotonic()
            try:
                logger.info(
                    "llm.router.dispatch provider=%s classification=%s",
                    provider.name,
                    cls.name,
                )
                result = await provider.generate(task)
            except ClassificationViolationError:
                # Should not happen because we filtered already, but if it
                # does we re-raise — never silently downgrade.
                await _audit_dispatch(
                    provider=provider.name,
                    classification=cls,
                    outcome="denied",
                    metadata={
                        "reason": "classification_violation",
                        "latency_ms": int((time.monotonic() - started) * 1000),
                    },
                )
                raise
            except ProviderUnavailable as exc:
                last_error = exc
                logger.warning(
                    "llm.router.provider_failed provider=%s error=%s",
                    provider.name,
                    exc,
                )
                await _audit_dispatch(
                    provider=provider.name,
                    classification=cls,
                    outcome="error",
                    metadata={
                        "reason": "provider_unavailable",
                        "latency_ms": int((time.monotonic() - started) * 1000),
                    },
                )
                continue

            latency_ms = (
                result.latency_ms
                if result.latency_ms is not None
                else int((time.monotonic() - started) * 1000)
            )
            await _audit_dispatch(
                provider=provider.name,
                classification=cls,
                outcome="success",
                metadata={
                    "model": result.model,
                    "latency_ms": latency_ms,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                },
            )
            return result

        raise AllProvidersFailed(
            f"No provider could serve classification={cls.name}. "
            f"Last error: {last_error!r}"
        )


# Singleton instance used across the app. Tests can construct a new
# LLMRouter with custom providers.
llm_router = LLMRouter()


__all__ = ["LLMRouter", "llm_router"]
