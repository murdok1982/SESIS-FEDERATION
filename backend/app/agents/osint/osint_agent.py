from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from app.agents.osint.base import AgentContext, AgentResult, AgentRole, BaseAgent, Finding, FindingClassification
from app.services.osint.llm.prompts.osint import OSINT_SYSTEM_PROMPT

class OsintAgent(BaseAgent):
    role = AgentRole.OSINT
    allowed_tools = [
        "dns_lookup", "whois_query", "cert_search",
        "web_fetch", "web_search", "document_extract",
        "archive_lookup", "ip_geolocation",
    ]

    async def run(self, context: AgentContext) -> AgentResult:
        t0 = time.monotonic()
        entity_type = context.input_data.get("entity_type", "DOMAIN").upper()
        target = context.input_data.get("target") or context.input_data.get("query", "")

        if not target:
            return AgentResult(agent=self.role, success=False, error="No target specified")

        self.logger.info("osint_start", entity_type=entity_type, target=target)
        raw_results: list[dict] = []

        try:
            if entity_type == "DOMAIN":
                raw_results = await self._investigate_domain(target)
            elif entity_type == "IP":
                raw_results = await self._investigate_ip(target)
            elif entity_type == "EMAIL":
                raw_results = await self._investigate_email(target)
            elif entity_type in ("URL",):
                raw_results = await self._investigate_url(target)
            else:
                raw_results = await self._investigate_generic(target)
        except Exception as exc:
            self.logger.error("osint_error", error=str(exc))
            return AgentResult(agent=self.role, success=False, error=str(exc), duration_seconds=time.monotonic() - t0)

        # LLM analysis of raw results
        user_prompt = f"TARGET: {target} (type: {entity_type})\n\nRAW DATA:\n{json.dumps(raw_results, indent=2, default=str)}\n\nAnalyze, extract entities, and produce structured findings."
        try:
            analysis = await self._llm_reason(OSINT_SYSTEM_PROMPT, user_prompt, max_tokens=4000)
        except Exception:
            analysis = ""

        findings = self._build_findings(raw_results)
        entities = self._extract_entities(raw_results, entity_type, target)

        return AgentResult(
            agent=self.role,
            success=True,
            findings=findings,
            entities_extracted=entities,
            raw_output=analysis,
            duration_seconds=time.monotonic() - t0,
            tool_calls_made=self._tool_calls,
        )

    async def _investigate_domain(self, domain: str) -> list[dict]:
        results = []
        for record_type in ["A", "MX", "TXT", "NS", "SOA"]:
            r = await self._call_tool("dns_lookup", domain=domain, record_types=[record_type])
            if r["success"]:
                results.append({"tool": "dns_lookup", "record_type": record_type, **r})

        r = await self._call_tool("whois_query", target=domain)
        if r["success"]:
            results.append({"tool": "whois_query", **r})

        r = await self._call_tool("cert_search", domain=domain)
        if r["success"]:
            results.append({"tool": "cert_search", **r})

        r = await self._call_tool("web_fetch", url=f"https://{domain}")
        if r["success"]:
            results.append({"tool": "web_fetch", **r})

        r = await self._call_tool("archive_lookup", url=f"https://{domain}")
        if r["success"]:
            results.append({"tool": "archive_lookup", **r})

        return results

    async def _investigate_ip(self, ip: str) -> list[dict]:
        results = []
        r = await self._call_tool("ip_geolocation", ip=ip)
        if r["success"]:
            results.append({"tool": "ip_geolocation", **r})

        r = await self._call_tool("whois_query", target=ip)
        if r["success"]:
            results.append({"tool": "whois_rdap", **r})

        r = await self._call_tool("dns_lookup", domain=ip, record_types=["PTR"])
        if r["success"]:
            results.append({"tool": "dns_ptr", **r})

        return results

    async def _investigate_email(self, email: str) -> list[dict]:
        results = []
        r = await self._call_tool("web_search", query=f'"{email}"', num_results=10)
        if r["success"]:
            results.append({"tool": "web_search", **r})

        domain = email.split("@")[-1] if "@" in email else ""
        if domain:
            domain_results = await self._investigate_domain(domain)
            results.extend(domain_results)
        return results

    async def _investigate_url(self, url: str) -> list[dict]:
        results = []
        r = await self._call_tool("web_fetch", url=url)
        if r["success"]:
            results.append({"tool": "web_fetch", **r})

        r = await self._call_tool("document_extract", url=url)
        if r["success"]:
            results.append({"tool": "document_extract", **r})

        r = await self._call_tool("archive_lookup", url=url)
        if r["success"]:
            results.append({"tool": "archive_lookup", **r})
        return results

    async def _investigate_generic(self, query: str) -> list[dict]:
        r = await self._call_tool("web_search", query=query, num_results=15)
        return [{"tool": "web_search", **r}] if r["success"] else []

    def _build_findings(self, raw_results: list[dict]) -> list[Finding]:
        findings = []
        for r in raw_results:
            if not r.get("success"):
                continue
            findings.append(
                Finding(
                    finding_type=r.get("tool", "unknown"),
                    classification=FindingClassification.FACT,
                    confidence=0.9,
                    data=r.get("data", {}),
                    source=r.get("source", ""),
                    method=r.get("tool", ""),
                    timestamp_collected=datetime.now(timezone.utc),
                )
            )
        return findings

    def _extract_entities(self, raw_results: list[dict], entity_type: str, target: str) -> list[dict]:
        entities = [{"entity_type": entity_type, "value": target, "confidence_score": 0.95}]
        for r in raw_results:
            if r.get("tool") == "cert_search" and r.get("success"):
                data = r.get("data", {})
                for subdomain in data.get("subdomains", []):
                    entities.append({"entity_type": "DOMAIN", "value": subdomain, "confidence_score": 0.85})
        return entities
