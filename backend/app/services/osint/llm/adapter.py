"""LLM adapter with state-grade classification gating.

The adapter routes LLM completion requests through a chain of providers,
but enforces a hard rule:

- Tasks with classification >= CONFIDENTIAL MUST be served by a local
  provider (Ollama / vLLM / llama.cpp). External providers (OpenAI,
  Anthropic, OpenRouter) are marked ``forbidden_for_classified`` and
  refused for classified content, with fail-closed semantics.

- Tasks with classification < CONFIDENTIAL may use external providers
  ONLY when ``ENABLE_EXTERNAL_FALLBACK=true`` in settings AND the call
  passes through the explicit fallback chain — never silently.

The adapter NEVER logs prompt or completion content. It logs metadata
only (provider, model, classification, tokens, latency).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings, get_settings
from app.core.security.classification import ClassificationLevel
from app.services.osint.llm.providers.base import BaseLLMProvider, LLMMessage, LLMProvider, LLMResponse

logger = get_logger(__name__)

class ClassificationViolationError(PermissionError):
    """Raised when no provider can lawfully serve the task's classification."""

class AllProvidersFailed(RuntimeError):
    """Raised when every eligible provider failed or was unavailable."""

@dataclass(frozen=True)
class _ProviderMeta:
    """Metadata describing a provider for routing decisions."""

    name: str
    is_local: bool
    max_classification: ClassificationLevel
    forbidden_for_classified: bool

# ---------------------------------------------------------------------------
# Provider metadata registry — single source of truth for routing rules
# ---------------------------------------------------------------------------
# Local providers can serve any classification up to TOP_SECRET.
# External providers (data leaves the sovereign perimeter) are HARD-capped
# at UNCLASSIFIED — even when fallback is allowed, they can never receive
# CUI or higher content.

_PROVIDER_META: dict[str, _ProviderMeta] = {
    LLMProvider.OLLAMA: _ProviderMeta(
        name=LLMProvider.OLLAMA,
        is_local=True,
        max_classification=ClassificationLevel.TOP_SECRET,
        forbidden_for_classified=False,
    ),
    LLMProvider.OPENAI: _ProviderMeta(
        name=LLMProvider.OPENAI,
        is_local=False,
        max_classification=ClassificationLevel.UNCLASSIFIED,
        forbidden_for_classified=True,
    ),
    LLMProvider.ANTHROPIC: _ProviderMeta(
        name=LLMProvider.ANTHROPIC,
        is_local=False,
        max_classification=ClassificationLevel.UNCLASSIFIED,
        forbidden_for_classified=True,
    ),
    LLMProvider.OPENROUTER: _ProviderMeta(
        name=LLMProvider.OPENROUTER,
        is_local=False,
        max_classification=ClassificationLevel.UNCLASSIFIED,
        forbidden_for_classified=True,
    ),
}

@dataclass
class LLMTask:
    """A typed LLM request with explicit classification."""

    messages: list[LLMMessage]
    classification: ClassificationLevel = ClassificationLevel.UNCLASSIFIED
    operator_id: str | None = None
    tenant_id: str | None = None
    max_tokens: int = 2000
    temperature: float = 0.1
    timeout: int = 120
    provider: str | None = None  # override default chain
    model: str | None = None
    metadata: dict = field(default_factory=dict)

class LLMAdapter:
    """Sovereign-by-default LLM router with classification gating."""

    def __init__(self, config) -> None:
        self.config = config
        self.providers: dict[str, BaseLLMProvider] = {}
        self._total_cost_usd: float = 0.0
        self._total_tokens: int = 0
        self._init_providers()

    # ------------------------------------------------------------------
    # Provider initialisation
    # ------------------------------------------------------------------

    def _init_providers(self) -> None:
        from app.services.osint.llm.providers.ollama import OllamaProvider  # noqa: PLC0415

        # Ollama is the primary sovereign provider — always registered
        self.providers[LLMProvider.OLLAMA] = OllamaProvider(self.config)

        # External providers — registered only if configured AND the
        # external-fallback flag is enabled. This makes the policy
        # decision explicit at startup time.
        if getattr(self.config, "ENABLE_EXTERNAL_FALLBACK", False):
            if self.config.OPENAI_API_KEY:
                from app.services.osint.llm.providers.openai_provider import OpenAIProvider  # noqa: PLC0415
                self.providers[LLMProvider.OPENAI] = OpenAIProvider(self.config)

            if self.config.ANTHROPIC_API_KEY:
                from app.services.osint.llm.providers.anthropic_provider import AnthropicProvider  # noqa: PLC0415
                self.providers[LLMProvider.ANTHROPIC] = AnthropicProvider(self.config)

            if self.config.OPENROUTER_API_KEY:
                from app.services.osint.llm.providers.openrouter_provider import OpenRouterProvider  # noqa: PLC0415
                self.providers[LLMProvider.OPENROUTER] = OpenRouterProvider(self.config)
        else:
            logger.info(
                "llm.adapter.external_disabled",
                reason="ENABLE_EXTERNAL_FALLBACK=false — only local providers active",
            )

    # ------------------------------------------------------------------
    # Eligibility computation
    # ------------------------------------------------------------------

    def _eligible(self, task_classification: ClassificationLevel) -> list[str]:
        """Return providers that may LAWFULLY serve this classification.

        Filters by (a) max_classification cap and (b) the
        ``forbidden_for_classified`` flag combined with the requested level.
        """
        cls = ClassificationLevel.from_any(task_classification)
        out: list[str] = []
        for name, meta in _PROVIDER_META.items():
            if name not in self.providers:
                continue
            # Hard cap: provider's max_classification must accept the request
            if cls > meta.max_classification:
                continue
            # Belt-and-braces: classified content never goes to forbidden providers
            if cls > ClassificationLevel.UNCLASSIFIED and meta.forbidden_for_classified:
                continue
            out.append(name)
        return out

    # ------------------------------------------------------------------
    # Main entry point — typed task interface
    # ------------------------------------------------------------------

    async def complete_task(self, task: LLMTask) -> LLMResponse:
        """Execute an LLMTask with classification gating.

        Raises:
            ClassificationViolationError: no provider may lawfully handle
                the task's classification (e.g. CONFIDENTIAL request but
                only OpenAI configured).
            AllProvidersFailed: every eligible provider failed.
        """
        cls = ClassificationLevel.from_any(task.classification)

        # Build eligible set first — fail fast if no provider qualifies
        eligible = self._eligible(cls)
        if not eligible:
            raise ClassificationViolationError(
                f"No registered provider may handle classification={cls.name}. "
                f"Configure a local provider (Ollama) before retrying."
            )

        # State-grade defensive rule: at CONFIDENTIAL+ we require at least
        # one LOCAL provider in the eligible set. This is redundant with
        # forbidden_for_classified filtering above but documents intent.
        if cls >= ClassificationLevel.CONFIDENTIAL:
            local_eligible = [
                n for n in eligible if _PROVIDER_META[n].is_local
            ]
            if not local_eligible:
                raise ClassificationViolationError(
                    f"classification={cls.name} requires a local provider; "
                    f"none eligible. Refusing to proceed."
                )
            eligible = local_eligible

        # If the task names an explicit provider, honour it if eligible
        if task.provider:
            if task.provider not in eligible:
                raise ClassificationViolationError(
                    f"Requested provider {task.provider!r} is not eligible for "
                    f"classification={cls.name}."
                )
            eligible = [task.provider]

        # Try eligible providers in order
        last_error: Exception | None = None
        for name in eligible:
            provider_instance = self.providers[name]
            try:
                model = task.model or self._default_model_for(name)
                logger.info(
                    "llm.adapter.dispatch",
                    provider=name,
                    model=model,
                    classification=cls.name,
                    operator_id=task.operator_id,
                    tenant_id=task.tenant_id,
                )
                response = await provider_instance.complete(
                    messages=task.messages,
                    model=model,
                    max_tokens=task.max_tokens,
                    temperature=task.temperature,
                    timeout=task.timeout,
                )
                self._total_cost_usd += response.cost_usd
                self._total_tokens += response.input_tokens + response.output_tokens
                logger.info(
                    "llm.adapter.complete",
                    provider=name,
                    in_tokens=response.input_tokens,
                    out_tokens=response.output_tokens,
                    cost_usd=round(response.cost_usd, 6),
                    duration_ms=round(response.duration_ms, 1),
                    classification=cls.name,
                )
                return response
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "llm.adapter.provider_failed",
                    provider=name,
                    classification=cls.name,
                    error=str(exc),
                )
                continue

        raise AllProvidersFailed(
            f"All eligible providers failed for classification={cls.name}. "
            f"Last error: {last_error!r}"
        )

    # ------------------------------------------------------------------
    # Backward-compatible legacy entrypoint
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[LLMMessage],
        provider: str | None = None,
        model: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.1,
        timeout: int = 120,
        fallback: bool = True,
        classification: ClassificationLevel | int | str = ClassificationLevel.UNCLASSIFIED,
    ) -> LLMResponse:
        """Backward-compatible wrapper. New code should use complete_task().

        Adds the ``classification`` kwarg (defaults to UNCLASSIFIED) so
        existing call sites continue to work without modification, but
        any caller that wants classified routing gets it by passing the
        correct level.
        """
        task = LLMTask(
            messages=messages,
            classification=ClassificationLevel.from_any(classification),
            provider=provider,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        try:
            return await self.complete_task(task)
        except ClassificationViolationError:
            # Never silently downgrade — re-raise so the caller sees it
            raise
        except AllProvidersFailed as exc:
            if not fallback:
                raise
            logger.warning("llm.adapter.no_fallback_left", error=str(exc))
            raise

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _default_model_for(self, provider: str) -> str:
        if provider == LLMProvider.OLLAMA:
            return getattr(self.config, "OLLAMA_DEFAULT_MODEL", "llama3.1")
        if provider == LLMProvider.OPENAI:
            return getattr(self.config, "OPENAI_DEFAULT_MODEL", "gpt-4o-mini")
        if provider == LLMProvider.ANTHROPIC:
            return getattr(self.config, "ANTHROPIC_DEFAULT_MODEL", "claude-haiku-4-5-20251001")
        if provider == LLMProvider.OPENROUTER:
            return getattr(
                self.config,
                "OPENROUTER_DEFAULT_MODEL",
                "meta-llama/llama-3.1-8b-instruct:free",
            )
        return self.config.LLM_DEFAULT_MODEL

    def get_usage_stats(self) -> dict:
        return {
            "total_cost_usd": round(self._total_cost_usd, 6),
            "total_tokens": self._total_tokens,
            "providers_active": list(self.providers.keys()),
        }

__all__ = [
    "LLMAdapter",
    "LLMTask",
    "ClassificationViolationError",
    "AllProvidersFailed",
]
