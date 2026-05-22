from __future__ import annotations

import time
from datetime import datetime, timezone

from app.agents.osint.base import AgentContext, AgentResult, AgentRole, BaseAgent, Finding, FindingClassification

class TimelineAgent(BaseAgent):
    role = AgentRole.TIMELINE
    allowed_tools: list[str] = []

    async def run(self, context: AgentContext) -> AgentResult:
        t0 = time.monotonic()
        evidence_list = context.input_data.get("evidence", [])

        self.logger.info("timeline_start", evidence_count=len(evidence_list))
        events: list[dict] = []

        for ev in evidence_list:
            ts = ev.get("collected_at") or ev.get("timestamp")
            if not ts:
                continue
            events.append({
                "timestamp": ts,
                "event_type": ev.get("evidence_type", "UNKNOWN"),
                "description": ev.get("title", ""),
                "source": ev.get("source_url", ""),
                "evidence_id": ev.get("id", ""),
            })

        events.sort(key=lambda x: x.get("timestamp", ""))

        geo_points: list[dict] = []
        for ev in evidence_list:
            raw = ev.get("raw_data", {})
            lat = raw.get("lat") or raw.get("latitude")
            lon = raw.get("lon") or raw.get("longitude")
            if lat and lon:
                geo_points.append({
                    "lat": float(lat),
                    "lon": float(lon),
                    "label": ev.get("title", ""),
                    "timestamp": ev.get("collected_at", ""),
                    "evidence_id": ev.get("id", ""),
                })

        return AgentResult(
            agent=self.role,
            success=True,
            findings=[
                Finding(
                    finding_type="timeline",
                    classification=FindingClassification.FACT,
                    confidence=0.95,
                    data={"events": events, "geo_points": geo_points},
                    source="internal",
                    method="timeline_analysis",
                    timestamp_collected=datetime.now(timezone.utc),
                )
            ],
            duration_seconds=time.monotonic() - t0,
        )
