from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from app.agents.osint.base import AgentContext, AgentResult, AgentRole, BaseAgent, Finding, FindingClassification
from app.services.osint.llm.prompts.socmint import SOCMINT_SYSTEM_PROMPT

class SocmintAgent(BaseAgent):
    role = AgentRole.SOCMINT
    allowed_tools = ["web_fetch", "web_search", "archive_lookup", "social_profile_fetch"]

    PLATFORMS = ["twitter", "github", "reddit", "instagram", "telegram", "youtube", "linkedin"]

    async def run(self, context: AgentContext) -> AgentResult:
        t0 = time.monotonic()
        handle = context.input_data.get("handle") or context.input_data.get("target", "")
        platforms = context.input_data.get("platforms", self.PLATFORMS)
        search_query = context.input_data.get("query", handle)

        if not handle and not search_query:
            return AgentResult(agent=self.role, success=False, error="No handle or query specified")

        self.logger.info("socmint_start", handle=handle, platforms=platforms)
        raw_results: list[dict] = []

        # Profile fetch on requested platforms
        if handle:
            r = await self._call_tool("social_profile_fetch", handle=handle, platforms=platforms)
            if r["success"]:
                raw_results.append({"tool": "social_profile_fetch", **r})

        # Web search for cross-platform discovery
        if search_query:
            r = await self._call_tool("web_search", query=f'"{search_query}" site:twitter.com OR site:github.com OR site:reddit.com', num_results=10)
            if r["success"]:
                raw_results.append({"tool": "web_search_social", **r})

        # Archive lookup for deleted profiles
        if handle:
            for platform in ["twitter.com", "github.com"]:
                r = await self._call_tool("archive_lookup", url=f"https://{platform}/{handle}")
                if r["success"]:
                    raw_results.append({"tool": "archive_lookup", "platform": platform, **r})

        # LLM synthesis
        user_prompt = f"HANDLE: {handle}\nPLATFORMS: {platforms}\n\nCOLLECTED DATA:\n{json.dumps(raw_results, indent=2, default=str)}\n\nAnalyze public profiles and cross-platform presence."
        try:
            analysis = await self._llm_reason(SOCMINT_SYSTEM_PROMPT, user_prompt, max_tokens=4000)
        except Exception:
            analysis = ""

        findings = self._build_findings(raw_results)
        entities = self._extract_entities(raw_results, handle)

        return AgentResult(
            agent=self.role,
            success=True,
            findings=findings,
            entities_extracted=entities,
            raw_output=analysis,
            duration_seconds=time.monotonic() - t0,
            tool_calls_made=self._tool_calls,
        )

    def _build_findings(self, raw_results: list[dict]) -> list[Finding]:
        return [
            Finding(
                finding_type=r.get("tool", "socmint"),
                classification=FindingClassification.FACT,
                confidence=0.75,
                data=r.get("data", {}),
                source=r.get("source", ""),
                method=r.get("tool", ""),
                timestamp_collected=datetime.now(timezone.utc),
            )
            for r in raw_results
            if r.get("success")
        ]

    def _extract_entities(self, raw_results: list[dict], handle: str) -> list[dict]:
        entities = []
        if handle:
            entities.append({"entity_type": "HANDLE", "value": handle, "confidence_score": 0.9})
        for r in raw_results:
            data = r.get("data", {})
            if isinstance(data, dict):
                for platform, profile in data.items():
                    if isinstance(profile, dict) and profile.get("exists"):
                        entities.append({
                            "entity_type": "HANDLE",
                            "value": f"{platform}:{handle}",
                            "attributes": profile,
                            "confidence_score": 0.85,
                        })
        return entities
