from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.agents.osint.base import AgentContext, AgentResult, AgentRole, BaseAgent, Finding, FindingClassification
from app.services.osint.llm.prompts.coordinator import COORDINATOR_SYSTEM_PROMPT

class CoordinatorAgent(BaseAgent):
    role = AgentRole.COORDINATOR
    allowed_tools: list[str] = []

    async def run(self, context: AgentContext) -> AgentResult:
        t0 = time.monotonic()
        task_description = context.input_data.get("task_description", "")
        self.logger.info("coordinator_start", case_id=context.case_id, job_id=context.job_id)

        user_prompt = f"""
CASE ID: {context.case_id}
AUTHORIZED SCOPE: {', '.join(context.scope) if context.scope else 'public sources only'}
TASK: {task_description}

Produce the execution plan as strict JSON.
"""
        try:
            raw = await self._llm_reason(COORDINATOR_SYSTEM_PROMPT, user_prompt, max_tokens=3000)
        except Exception as exc:
            return AgentResult(
                agent=self.role,
                success=False,
                error=f"LLM call failed: {exc}",
                duration_seconds=time.monotonic() - t0,
            )

        plan = self._parse_plan(raw)
        if not plan:
            return AgentResult(
                agent=self.role,
                success=False,
                error="Could not parse execution plan from LLM output",
                raw_output=raw,
                duration_seconds=time.monotonic() - t0,
            )

        self.logger.info("coordinator_plan_ready", task_count=len(plan.get("tasks", [])))

        all_findings: list[Finding] = []
        all_entities: list[dict] = []

        # Execute tasks respecting depends_on
        completed_tasks: set[str] = set()
        task_results: dict[str, Any] = {}

        for task in plan.get("tasks", []):
            task_id = task.get("task_id", str(uuid.uuid4()))
            agent_name = task.get("agent", "")
            depends_on = task.get("depends_on", [])
            require_approval = task.get("require_approval", False)
            sensitive = task.get("sensitive", False)

            # Check dependencies
            if not all(dep in completed_tasks for dep in depends_on):
                self.logger.warning("task_deps_not_met", task_id=task_id)
                continue

            if require_approval:
                self.logger.info("task_pending_approval", task_id=task_id, agent=agent_name)
                completed_tasks.add(task_id)
                continue

            sub_agent = self._create_agent(agent_name)
            if not sub_agent:
                self.logger.warning("unknown_agent", agent=agent_name)
                completed_tasks.add(task_id)
                continue

            sub_context = AgentContext(
                case_id=context.case_id,
                job_id=context.job_id,
                operator_id=context.operator_id,
                scope=context.scope,
                input_data=task.get("input", {}),
            )

            try:
                result = await sub_agent.run(sub_context)
                task_results[task_id] = result
                all_findings.extend(result.findings)
                all_entities.extend(result.entities_extracted)
                self.logger.info(
                    "task_completed",
                    task_id=task_id,
                    agent=agent_name,
                    findings=len(result.findings),
                    success=result.success,
                )
            except Exception as exc:
                self.logger.error("task_failed", task_id=task_id, agent=agent_name, error=str(exc))

            completed_tasks.add(task_id)

        return AgentResult(
            agent=self.role,
            success=True,
            findings=all_findings,
            entities_extracted=all_entities,
            raw_output=json.dumps(plan),
            duration_seconds=time.monotonic() - t0,
        )

    def _parse_plan(self, raw: str) -> dict | None:
        raw = raw.strip()
        # Try to extract JSON from markdown code block
        if "```json" in raw:
            start = raw.index("```json") + 7
            end = raw.index("```", start)
            raw = raw[start:end].strip()
        elif "```" in raw:
            start = raw.index("```") + 3
            end = raw.index("```", start)
            raw = raw[start:end].strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _create_agent(self, agent_name: str) -> BaseAgent | None:
        from app.agents.osint.osint_agent import OsintAgent  # noqa: PLC0415
        from app.agents.osint.socmint_agent import SocmintAgent  # noqa: PLC0415
        from app.agents.osint.entity_resolver import EntityResolverAgent  # noqa: PLC0415
        from app.agents.osint.source_validator import SourceValidatorAgent  # noqa: PLC0415
        from app.agents.osint.reporter import ReporterAgent  # noqa: PLC0415
        from app.agents.osint.timeline_agent import TimelineAgent  # noqa: PLC0415

        mapping = {
            "osint_agent": OsintAgent,
            "socmint_agent": SocmintAgent,
            "entity_resolver": EntityResolverAgent,
            "source_validator": SourceValidatorAgent,
            "reporter": ReporterAgent,
            "timeline_agent": TimelineAgent,
        }
        cls = mapping.get(agent_name)
        if not cls:
            return None
        return cls(llm_adapter=self.llm, tool_registry=self.tools)
