from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.core.config import settings, get_settings

class AgentRole(str, Enum):
    COORDINATOR = "coordinator"
    OSINT = "osint_agent"
    SOCMINT = "socmint_agent"
    ENTITY_RESOLVER = "entity_resolver"
    SOURCE_VALIDATOR = "source_validator"
    REPORTER = "reporter"
    TIMELINE = "timeline_agent"

class FindingClassification(str, Enum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"

@dataclass
class AgentContext:
    case_id: str
    job_id: str
    operator_id: str
    scope: list[str]
    input_data: dict[str, Any]
    iteration: int = 0
    max_iterations: int = 10

@dataclass
class Finding:
    finding_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    finding_type: str = ""
    classification: FindingClassification = FindingClassification.FACT
    confidence: float = 0.7
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    method: str = ""
    timestamp_collected: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ""
    requires_human_review: bool = False

@dataclass
class AgentResult:
    agent: AgentRole
    success: bool
    findings: list[Finding] = field(default_factory=list)
    entities_extracted: list[dict[str, Any]] = field(default_factory=list)
    next_tasks: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    duration_seconds: float = 0.0
    tool_calls_made: int = 0
    tokens_used: int = 0
    raw_output: str = ""

class BaseAgent:
    role: AgentRole
    allowed_tools: list[str] = []

    def __init__(self, llm_adapter: Any, tool_registry: Any = None) -> None:
        self.llm = llm_adapter
        self.tools = tool_registry
        self.logger = get_logger(self.__class__.__name__)
        self._tool_calls = 0

    async def run(self, context: AgentContext) -> AgentResult:
        raise NotImplementedError

    async def _call_tool(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        if tool_name not in self.allowed_tools:
            raise PermissionError(f"Agent {self.role} is not allowed to use tool '{tool_name}'")
        if not self.tools:
            raise RuntimeError("No tool registry configured")
        tool = self.tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not registered")
        self._tool_calls += 1
        result = await tool.execute(**kwargs)
        return {"success": result.success, "data": result.data, "source": result.source, "error": result.error}

    async def _llm_reason(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 3000,
        temperature: float = 0.1,
    ) -> str:
        from app.services.osint.llm.providers.base import LLMMessage  # noqa: PLC0415

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]
        response = await self.llm.complete(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.content
