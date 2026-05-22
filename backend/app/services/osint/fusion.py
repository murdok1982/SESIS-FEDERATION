from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings, get_settings
from app.core.events import event_bus
from app.services.osint.graph_intel import GraphIntelligence, Node, Edge
from app.services.osint.darkweb import DarkWebResult
from app.services.osint.imint import ImageAnalysisResult
from app.services.osint.finint import FinancialProfile
from app.services.osint.cybint import IndicatorOfCompromise, ThreatReport

logger = get_logger(__name__)

@dataclass
class IntelligenceFusionResult:
    fusion_id: str
    timestamp: float
    input_sources: list[str]
    correlated_entities: list[dict[str, Any]]
    relationships_found: list[dict[str, Any]]
    threat_assessment: str
    confidence: float
    recommendations: list[str]
    graph_data: dict[str, Any]
    raw_findings: list[dict[str, Any]]

class MultiINTFusionEngine:
    """Multi-INT Fusion Engine — correlates data from all intelligence disciplines."""

    def __init__(self) -> None:
        self._graph = GraphIntelligence()
        self._fusion_results: list[IntelligenceFusionResult] = []

    async def fuse(
        self,
        target: str,
        osint_results: list[dict[str, Any]] | None = None,
        darkweb_results: list[DarkWebResult] | None = None,
        imint_results: list[ImageAnalysisResult] | None = None,
        finint_profiles: list[FinancialProfile] | None = None,
        cybint_iocs: list[IndicatorOfCompromise] | None = None,
        cybint_report: ThreatReport | None = None,
        social_graph: dict[str, Any] | None = None,
    ) -> IntelligenceFusionResult:
        fusion_id = f"fusion_{int(time.time())}"
        input_sources = []
        correlated = []
        relationships = []
        findings = []

        if osint_results:
            input_sources.append("OSINT")
            for result in osint_results:
                entity_id = f"osint_{result.get('id', target)}"
                self._graph.add_entity(
                    entity_id, target, "osint_target", result,
                )
                findings.append({"source": "OSINT", "data": result})

        if darkweb_results:
            input_sources.append("DARKWEB")
            for result in darkweb_results:
                if result.risk_score >= 7.0:
                    correlated.append({
                        "type": "darkweb_alert",
                        "source": result.source,
                        "risk": result.risk_score,
                        "url": result.url,
                    })
                    self._graph.add_entity(
                        f"darkweb_{result.source}", result.source, "darkweb_source",
                    )
                    self._graph.add_relationship(target, f"darkweb_{result.source}", "FOUND_IN")
                    relationships.append({"from": target, "to": result.source, "type": "FOUND_IN"})

        if imint_results:
            input_sources.append("IMINT")
            for result in imint_results:
                if result.gps_coordinates:
                    correlated.append({
                        "type": "geolocation",
                        "coords": result.gps_coordinates,
                        "image_hash": result.image_hash,
                    })
                if result.manipulation_detected:
                    correlated.append({
                        "type": "image_manipulation",
                        "image_hash": result.image_hash,
                    })
                findings.append({"source": "IMINT", "data": {"hash": result.image_hash, "risk": result.risk_score}})

        if finint_profiles:
            input_sources.append("FININT")
            for profile in finint_profiles:
                if profile.total_volume > 100000:
                    correlated.append({
                        "type": "high_value_financial",
                        "entity": profile.entity_name,
                        "volume": profile.total_volume,
                        "sanctions": profile.sanctions_match,
                    })
                if profile.sanctions_match:
                    self._graph.add_entity(
                        f"sanctions_{profile.entity_name}", profile.entity_name, "sanctioned_entity",
                    )
                    self._graph.add_relationship(target, f"sanctions_{profile.entity_name}", "FINANCIAL_LINK")
                    relationships.append({"from": target, "to": profile.entity_name, "type": "FINANCIAL_LINK"})

        if cybint_iocs:
            input_sources.append("CYBINT")
            for ioc in cybint_iocs:
                self._graph.add_entity(
                    f"ioc_{ioc.value[:12]}", ioc.value, f"ioc_{ioc.ioc_type.value}",
                    {"threat_level": ioc.threat_level.value, "confidence": ioc.confidence},
                )
                self._graph.add_relationship(target, f"ioc_{ioc.value[:12]}", "ASSOCIATED_WITH")
                relationships.append({"from": target, "to": ioc.value, "type": "ASSOCIATED_WITH"})

        if social_graph:
            input_sources.append("SOCMINT")
            for node_data in social_graph.get("nodes", []):
                self._graph.add_entity(
                    node_data.get("id", f"social_{len(self._graph._nodes)}"),
                    node_data.get("label", "Unknown"),
                    "social_account",
                    node_data,
                )
            for edge_data in social_graph.get("edges", []):
                self._graph.add_relationship(
                    edge_data.get("source", ""),
                    edge_data.get("target", ""),
                    edge_data.get("relationship", "CONNECTED_TO"),
                )

        threat_assessment = self._assess_threat(
            correlated, cybint_report, darkweb_results, finint_profiles, cybint_iocs,
        )
        confidence = self._calculate_confidence(correlated, input_sources)
        recommendations = self._generate_recommendations(
            correlated, threat_assessment, cybint_report, finint_profiles,
        )

        result = IntelligenceFusionResult(
            fusion_id=fusion_id,
            timestamp=time.time(),
            input_sources=input_sources,
            correlated_entities=correlated,
            relationships_found=relationships,
            threat_assessment=threat_assessment,
            confidence=confidence,
            recommendations=recommendations,
            graph_data=self._graph.to_dict(),
            raw_findings=findings,
        )

        self._fusion_results.append(result)

        await event_bus.publish(AtalayaEvent(
            event_type=EventType.THREAT_DETECTED,
            source="multi-int-fusion",
            data={
                "fusion_id": fusion_id,
                "target": target,
                "threat_assessment": threat_assessment,
                "confidence": confidence,
                "sources": input_sources,
            },
        ))

        return result

    def _assess_threat(
        self,
        correlated: list[dict],
        cybint_report: ThreatReport | None,
        darkweb_results: list[DarkWebResult] | None,
        finint_profiles: list[FinancialProfile] | None,
        cybint_iocs: list[IndicatorOfCompromise] | None,
    ) -> str:
        indicators = []

        high_risk_darkweb = [r for r in (darkweb_results or []) if r.risk_score >= 7.0]
        if high_risk_darkweb:
            indicators.append(f"{len(high_risk_darkweb)} high-risk dark web findings")

        if finint_profiles:
            sanctioned = [p for p in finint_profiles if p.sanctions_match]
            if sanctioned:
                indicators.append(f"{len(sanctioned)} sanctions matches")

        if cybint_iocs:
            critical = [i for i in cybint_iocs if i.threat_level.value in ("critical", "high")]
            if critical:
                indicators.append(f"{len(critical)} high/critical IOCs")

        if cybint_report and cybint_report.threat_level.value in ("critical", "high"):
            indicators.append(f"Cyber threat level: {cybint_report.threat_level.value}")

        if not indicators:
            return "No significant threats identified. Continue monitoring."

        return "THREAT INDICATORS: " + "; ".join(indicators)

    def _calculate_confidence(self, correlated: list[dict], sources: list[str]) -> float:
        base = 0.3
        base += len(sources) * 0.1
        base += len(correlated) * 0.05
        return min(base, 1.0)

    def _generate_recommendations(
        self,
        correlated: list[dict],
        threat: str,
        cybint_report: ThreatReport | None,
        finint_profiles: list[FinancialProfile] | None,
    ) -> list[str]:
        recs = ["Continue monitoring target for changes"]

        if "sanctions" in threat.lower():
            recs.append("IMMEDIATE: Escalate to compliance team for sanctions review")
            recs.append("Freeze any financial transactions associated with target")

        if "cyber" in threat.lower() or "ioc" in threat.lower():
            recs.append("Block identified IOCs at network perimeter")
            recs.append("Conduct threat hunting across infrastructure")

        if any(c.get("type") == "geolocation" for c in correlated):
            recs.append("Correlate GPS coordinates with known facilities")

        if any(c.get("type") == "image_manipulation" for c in correlated):
            recs.append("Forensic analysis required for manipulated images")

        if cybint_report:
            recs.extend(cybint_report.recommendations[:3])

        return recs

    def get_fusion_history(self) -> list[IntelligenceFusionResult]:
        return self._fusion_results

    def export_report(self, fusion_id: str) -> dict[str, Any] | None:
        for result in self._fusion_results:
            if result.fusion_id == fusion_id:
                return {
                    "fusion_id": result.fusion_id,
                    "timestamp": result.timestamp,
                    "input_sources": result.input_sources,
                    "correlated_entities": result.correlated_entities,
                    "relationships_found": result.relationships_found,
                    "threat_assessment": result.threat_assessment,
                    "confidence": result.confidence,
                    "recommendations": result.recommendations,
                    "graph_data": result.graph_data,
                }
        return None

fusion_engine = MultiINTFusionEngine()
