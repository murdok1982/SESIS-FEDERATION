"""
vLLM local provider.

Targets a self-hosted vLLM server that exposes an OpenAI-compatible
``/v1/chat/completions`` endpoint. Because the inference happens on
infrastructure controlled by the operator, vLLM is permitted for
classified tasks up to SECRET.

The provider is only enabled when ``VLLM_BASE_URL`` is set in the
environment. When ``VLLM_BASE_URL`` is empty, ``is_available()``
returns False and the router skips it transparently.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.classification import ClassificationLevel
from app.core.config import settings
from app.services.intel.llm.base import LLMProvider, LLMResult, LLMTask
from app.services.intel.llm.exceptions import ProviderUnavailable

logger = logging.getLogger(__name__)


class VLLMProvider(LLMProvider):
    """Local LLM provider backed by a vLLM OpenAI-compatible server."""

    name = "vllm"
    forbidden_for_classified = False
    max_classification = ClassificationLevel.SECRET

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.VLLM_BASE_URL or "").rstrip("/")
        self.default_model = model or settings.VLLM_MODEL
        self.timeout = timeout or settings.VLLM_TIMEOUT

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/v1/models")
                return resp.status_code == 200
        except (httpx.HTTPError, OSError) as exc:
            logger.debug("vLLM availability probe failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def _generate(self, task: LLMTask) -> LLMResult:
        if not self.base_url:
            raise ProviderUnavailable("vLLM base_url not configured")

        model = task.model or self.default_model
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": task.system_prompt},
                {"role": "user", "content": task.prompt},
            ],
            "temperature": task.temperature,
            "stream": False,
        }
        if task.max_tokens is not None:
            payload["max_tokens"] = task.max_tokens

        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions", json=payload
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, OSError) as exc:
            raise ProviderUnavailable(f"vLLM request failed: {exc!r}") from exc

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailable(f"vLLM response malformed: {exc!r}") from exc

        usage = data.get("usage") or {}
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "llm.vllm.ok model=%s classification=%s latency_ms=%d "
            "prompt_tokens=%s completion_tokens=%s",
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


__all__ = ["VLLMProvider"]
