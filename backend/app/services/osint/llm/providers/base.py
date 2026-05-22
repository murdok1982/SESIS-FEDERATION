from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"

@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str

@dataclass
class LLMResponse:
    content: str
    provider: LLMProvider
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: float

class BaseLLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        model: str,
        max_tokens: int,
        temperature: float,
        timeout: int,
    ) -> LLMResponse: ...

    @abstractmethod
    def list_models(self) -> list[str]: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
