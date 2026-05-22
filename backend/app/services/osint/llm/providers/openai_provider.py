from __future__ import annotations

import time

from app.services.osint.llm.providers.base import BaseLLMProvider, LLMMessage, LLMProvider, LLMResponse

_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.0, 30.0),
}

class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, config) -> None:
        import openai  # noqa: PLC0415
        self.client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self.default_model = config.OPENAI_DEFAULT_MODEL

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str,
        max_tokens: int = 2000,
        temperature: float = 0.1,
        timeout: int = 120,
    ) -> LLMResponse:
        t0 = time.monotonic()
        response = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        duration_ms = (time.monotonic() - t0) * 1000
        content = response.choices[0].message.content or ""
        in_tok = response.usage.prompt_tokens if response.usage else 0
        out_tok = response.usage.completion_tokens if response.usage else 0

        price_in, price_out = _PRICING.get(model, (0.0, 0.0))
        cost = (in_tok / 1_000_000 * price_in) + (out_tok / 1_000_000 * price_out)

        return LLMResponse(
            content=content,
            provider=LLMProvider.OPENAI,
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            duration_ms=duration_ms,
        )

    def list_models(self) -> list[str]:
        return list(_PRICING.keys())

    async def health_check(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False
