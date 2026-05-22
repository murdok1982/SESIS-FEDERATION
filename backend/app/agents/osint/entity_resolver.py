from __future__ import annotations

import json
import time
from typing import Any

from app.agents.osint.base import AgentContext, AgentResult, AgentRole, BaseAgent
from app.services.osint.llm.prompts.entity_resolution import ENTITY_RESOLUTION_SYSTEM_PROMPT

class EntityResolverAgent(BaseAgent):
    role = AgentRole.ENTITY_RESOLVER
    allowed_tools: list[str] = []

    async def run(self, context: AgentContext) -> AgentResult:
        t0 = time.monotonic()
        entities = context.input_data.get("entities", [])

        if not entities:
            return AgentResult(agent=self.role, success=True, duration_seconds=time.monotonic() - t0)

        self.logger.info("entity_resolver_start", entity_count=len(entities))

        # Exact dedup first (fast, no LLM needed)
        exact_groups = self._exact_dedup(entities)

        # LLM for fuzzy/attribute matching
        user_prompt = f"ENTITIES TO ANALYZE:\n{json.dumps(entities, indent=2, default=str)}\n\nIdentify duplicates, fuzzy matches, and relationships. Output strict JSON."
        try:
            analysis = await self._llm_reason(ENTITY_RESOLUTION_SYSTEM_PROMPT, user_prompt, max_tokens=4000)
        except Exception:
            analysis = ""

        return AgentResult(
            agent=self.role,
            success=True,
            raw_output=analysis,
            next_tasks=[{"action": "merge_proposals", "data": exact_groups}],
            duration_seconds=time.monotonic() - t0,
        )

    def _exact_dedup(self, entities: list[dict[str, Any]]) -> list[dict]:
        seen: dict[str, str] = {}
        proposals = []
        for entity in entities:
            key = f"{entity.get('entity_type', '')}:{entity.get('value', '').lower().strip()}"
            if key in seen:
                proposals.append({
                    "source_id": entity.get("id", ""),
                    "target_id": seen[key],
                    "confidence": 0.99,
                    "method": "exact",
                    "requires_human_review": False,
                })
            else:
                seen[key] = entity.get("id", "")
        return proposals
