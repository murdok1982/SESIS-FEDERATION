"""
OpenRouter external provider — PROHIBITED FOR CLASSIFIED data.

This provider talks to ``https://openrouter.ai`` which is operated
from US infrastructure. Because the operator does NOT control where
the inference happens, this provider is ONLY valid for tasks marked
``ClassificationLevel.PUBLIC`` (e.g. open-source news synthesis,
public economic indicators).

The provider self-marks ``forbidden_for_classified = True``. The
base class will raise :class:`ClassificationViolationError` for any
task above PUBLIC, regardless of router configuration.
"""

from __future__ import annotations

import logging
import time

import httpx

from app.core.classification import ClassificationLevel
from app.core.config import settings
from app.services.intel.llm.base import LLMProvider, LLMResult, LLMTask
from app.services.intel.llm.exceptions import ProviderUnavailable

logger = logging.getLogger(__name__)


class OpenRouterProvider(LLMProvider):
    """External LLM router. PUBLIC-only."""

    name = "openrouter"
    forbidden_for_classified = True
    max_classification = ClassificationLevel.PUBLIC

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str | None = None,
        referer: str = "https://globalintelligence.io",
        title: str = "Global Intelligence Platform",
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.OPENROUTER_API_KEY
        self.default_model = default_model or settings.OPENROUTER_DEFAULT_MODEL
        self.referer = referer
        self.title = title

    async def is_available(self) -> bool:
        # No api key -> not configured -> not available.
        if not self.api_key:
            return False
        # Respect the global toggle. We do not ping OpenRouter from a
        # state-grade deployment unnecessarily.
        if not settings.ENABLE_OPENROUTER_FALLBACK:
            return False
        return True

    async def _generate(self, task: LLMTask) -> LLMResult:
        if not self.api_key:
            raise ProviderUnavailable("OPENROUTER_API_KEY not configured")

        model = task.model or self.default_model
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.referer,
            "X-Title": self.title,
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": task.system_prompt},
                {"role": "user", "content": task.prompt},
            ],
            "temperature": task.temperature,
        }
        if task.max_tokens is not None:
            payload["max_tokens"] = task.max_tokens

        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(self.BASE_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, OSError) as exc:
            raise ProviderUnavailable(f"OpenRouter request failed: {exc!r}") from exc

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailable(f"OpenRouter response malformed: {exc!r}") from exc

        usage = data.get("usage") or {}
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.warning(
            "llm.openrouter.ok model=%s classification=%s latency_ms=%d "
            "prompt_tokens=%s completion_tokens=%s "
            "[external-provider; data left sovereign perimeter]",
            model,
            task.classification.name,
            latency_ms,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )
        return LLMResult(
            text=text,
            provider=self.name,
            model=model,
            classification=task.classification,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=latency_ms,
        )


__all__ = ["OpenRouterProvider"]
