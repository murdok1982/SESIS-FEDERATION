from __future__ import annotations

import time

import httpx

from app.services.osint.llm.providers.base import BaseLLMProvider, LLMMessage, LLMProvider, LLMResponse

class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def __init__(self, config) -> None:
        self.base_url = config.OLLAMA_BASE_URL
        self._models: list[str] = []

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str,
        max_tokens: int = 2000,
        temperature: float = 0.1,
        timeout: int = 120,
    ) -> LLMResponse:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        duration_ms = (time.monotonic() - t0) * 1000
        content = data.get("message", {}).get("content", "")
        eval_count = data.get("eval_count", 0)
        prompt_eval_count = data.get("prompt_eval_count", 0)

        return LLMResponse(
            content=content,
            provider=LLMProvider.OLLAMA,
            model=model,
            input_tokens=prompt_eval_count,
            output_tokens=eval_count,
            cost_usd=0.0,
            duration_ms=duration_ms,
        )

    def list_models(self) -> list[str]:
        return self._models

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    self._models = [m["name"] for m in resp.json().get("models", [])]
                    return True
        except Exception:
            pass
        return False
