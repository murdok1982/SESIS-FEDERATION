"""
Ollama local provider.

Talks HTTP to a local Ollama daemon (default
``http://ollama:11434``). Ollama keeps models on disk and serves
them through ``/api/chat``. Because the daemon runs inside the
operator's perimeter, this provider is safe for classified tasks
up to SECRET.

This implementation deliberately avoids the ``ollama`` Python SDK
to keep the dependency surface small — httpx is already a transitive
dependency of FastAPI's test client.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.classification import ClassificationLevel
from app.core.config import settings
from app.services.intel.llm.base import LLMProvider, LLMResult, LLMTask
from app.services.intel.llm.exceptions import ProviderUnavailable

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Local LLM provider backed by an Ollama daemon."""

    name = "ollama"
    forbidden_for_classified = False
    max_classification = ClassificationLevel.SECRET

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        max_retries: int = 3,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.default_model = model or settings.OLLAMA_MODEL
        self.timeout = timeout or settings.OLLAMA_TIMEOUT
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        url = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except (httpx.HTTPError, OSError) as exc:
            logger.debug("Ollama availability probe failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def _generate(self, task: LLMTask) -> LLMResult:
        model = task.model or self.default_model
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": task.system_prompt},
                {"role": "user", "content": task.prompt},
            ],
            "stream": False,
            "options": {
                "temperature": task.temperature,
            },
        }
        if task.max_tokens is not None:
            payload["options"]["num_predict"] = task.max_tokens

        url = f"{self.base_url}/api/chat"
        attempt = 0
        delay = 1.0
        last_exc: Exception | None = None

        started = time.monotonic()
        while attempt < self.max_retries:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                text = (data.get("message") or {}).get("content", "") or ""
                latency_ms = int((time.monotonic() - started) * 1000)
                logger.info(
                    "llm.ollama.ok model=%s classification=%s latency_ms=%d "
                    "prompt_eval=%s eval=%s",
                    model,
                    task.classification.name,
                    latency_ms,
                    data.get("prompt_eval_count"),
                    data.get("eval_count"),
                )
                return LLMResult(
                    text=text,
                    provider=self.name,
                    model=model,
                    classification=task.classification,
                    prompt_tokens=data.get("prompt_eval_count"),
                    completion_tokens=data.get("eval_count"),
                    latency_ms=latency_ms,
                )
            except (httpx.HTTPError, OSError) as exc:
                last_exc = exc
                logger.warning(
                    "llm.ollama.retry attempt=%d/%d error=%s",
                    attempt,
                    self.max_retries,
                    exc.__class__.__name__,
                )
                if attempt >= self.max_retries:
                    break
                await asyncio.sleep(delay)
                delay *= 2

        raise ProviderUnavailable(
            f"Ollama provider failed after {self.max_retries} attempts: {last_exc!r}"
        )


__all__ = ["OllamaProvider"]
