from __future__ import annotations

import time

import httpx

from app.services.osint.llm.providers.base import BaseLLMProvider, LLMMessage, LLMProvider, LLMResponse

class OpenRouterProvider(BaseLLMProvider):
    name = "openrouter"
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, config) -> None:
        self.api_key = config.OPENROUTER_API_KEY
        self.default_model = config.OPENROUTER_DEFAULT_MODEL

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
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Title": "Atalaya OSINT Platform",
            "Content-Type": "application/json",
        }
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{self.BASE_URL}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        duration_ms = (time.monotonic() - t0) * 1000
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)

        return LLMResponse(
            content=content,
            provider=LLMProvider.OPENROUTER,
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=0.0,
            duration_ms=duration_ms,
        )

    def list_models(self) -> list[str]:
        return [self.default_model]

    async def health_check(self) -> bool:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.BASE_URL}/models", headers=headers)
                return resp.status_code == 200
        except Exception:
            return False
