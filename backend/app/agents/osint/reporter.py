from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from app.agents.osint.base import AgentContext, AgentResult, AgentRole, BaseAgent
from app.core.config import settings
from app.services.osint.llm.prompts.reporting import REPORTING_SYSTEM_PROMPT

class ReporterAgent(BaseAgent):
    role = AgentRole.REPORTER
    allowed_tools: list[str] = []

    async def run(self, context: AgentContext) -> AgentResult:
        t0 = time.monotonic()
        report_type = context.input_data.get("report_type", "executive_summary")
        case_id = context.case_id
        entity_ids = context.input_data.get("entity_ids", [])
        evidence_data = context.input_data.get("evidence", [])
        report_format = context.input_data.get("format", "MARKDOWN")

        self.logger.info("reporter_start", report_type=report_type, case_id=case_id)

        user_prompt = f"""
REPORT TYPE: {report_type}
CASE ID: {case_id}
DATE: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
ENTITY IDS COVERED: {entity_ids}

EVIDENCE AND FINDINGS:
{json.dumps(evidence_data[:50], indent=2, default=str)}

Generate a complete professional intelligence report in Markdown format.
Follow the mandatory structure from your system prompt exactly.
"""
        try:
            report_content = await self._llm_reason(REPORTING_SYSTEM_PROMPT, user_prompt, max_tokens=6000, temperature=0.2)
        except Exception as exc:
            return AgentResult(agent=self.role, success=False, error=str(exc), duration_seconds=time.monotonic() - t0)

        # Save report to disk
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        case_dir = os.path.join(settings.REPORTS_STORAGE_PATH, case_id)
        os.makedirs(case_dir, exist_ok=True)
        file_path = os.path.join(case_dir, f"{ts}_{report_type}.md")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        word_count = len(report_content.split())
        self.logger.info("report_saved", file_path=file_path, word_count=word_count)

        return AgentResult(
            agent=self.role,
            success=True,
            raw_output=report_content,
            next_tasks=[{
                "action": "save_report",
                "file_path": file_path,
                "word_count": word_count,
                "report_type": report_type,
            }],
            duration_seconds=time.monotonic() - t0,
        )
