from __future__ import annotations

import json
import time

from app.agents.osint.base import AgentContext, AgentResult, AgentRole, BaseAgent
from app.services.osint.llm.prompts.source_validation import SOURCE_VALIDATION_SYSTEM_PROMPT

class SourceValidatorAgent(BaseAgent):
    role = AgentRole.SOURCE_VALIDATOR
    allowed_tools: list[str] = []

    async def run(self, context: AgentContext) -> AgentResult:
        t0 = time.monotonic()
        findings = context.input_data.get("findings", [])

        if not findings:
            return AgentResult(agent=self.role, success=True, duration_seconds=time.monotonic() - t0)

        self.logger.info("source_validator_start", finding_count=len(findings))

        user_prompt = f"FINDINGS TO VALIDATE:\n{json.dumps(findings, indent=2, default=str)}\n\nAssess reliability, corroboration, and contradictions. Output strict JSON."
        try:
            analysis = await self._llm_reason(SOURCE_VALIDATION_SYSTEM_PROMPT, user_prompt, max_tokens=4000)
        except Exception as exc:
            return AgentResult(agent=self.role, success=False, error=str(exc), duration_seconds=time.monotonic() - t0)

        return AgentResult(
            agent=self.role,
            success=True,
            raw_output=analysis,
            duration_seconds=time.monotonic() - t0,
        )
