from __future__ import annotations

import time

from app.services.osint.llm.providers.base import BaseLLMProvider, LLMMessage, LLMProvider, LLMResponse

_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.25, 1.25),
}

class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(self, config) -> None:
        import anthropic  # noqa: PLC0415
        self.client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
        self.default_model = config.ANTHROPIC_DEFAULT_MODEL

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str,
        max_tokens: int = 2000,
        temperature: float = 0.1,
        timeout: int = 120,
    ) -> LLMResponse:
        # Anthropic uses system as separate param
        system_content = ""
        user_messages = []
        for m in messages:
            if m.role == "system":
                system_content = m.content
            else:
                user_messages.append({"role": m.role, "content": m.content})

        t0 = time.monotonic()
        response = await self.client.messages.create(
            model=model,
            system=system_content or "You are a helpful assistant.",
            messages=user_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        duration_ms = (time.monotonic() - t0) * 1000
        content = response.content[0].text if response.content else ""
        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens

        price_in, price_out = _PRICING.get(model, (0.0, 0.0))
        cost = (in_tok / 1_000_000 * price_in) + (out_tok / 1_000_000 * price_out)

        return LLMResponse(
            content=content,
            provider=LLMProvider.ANTHROPIC,
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
