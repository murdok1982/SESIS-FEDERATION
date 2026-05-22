"""
Intelligence Fusion Service — Multi-INT correlation and product generation.

Correlates events by geo-proximity, time window, and entity identity.
Produces standard NATO intelligence products: INTSUM, SITREP, THREATSUM.
"""
import datetime
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db.models.persistence import (
    Alert,
    Event,
    IntelligenceProduct,
    IntelFusionRecord,
)
from .military_brain import military_brain

logger = logging.getLogger("sesis.intel_fusion")

ProductType = Literal["INTSUM", "SITREP", "THREATSUM", "COA_BRIEF", "STRAT_BRIEF"]
IntelSource = Literal["HUMINT", "SIGINT", "IMINT", "OSINT", "CYBER", "SATINT", "ELINT"]


@dataclass
class FusedIntelligence:
    fusion_id: str
    source_events: list[dict[str, Any]]
    entity_id: str | None
    fusion_score: float  # 0.0 – 1.0
    correlated_items: list[dict[str, Any]]
    assessment: dict[str, Any]
    classification: str
    created_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fusion_id": self.fusion_id,
            "entity_id": self.entity_id,
            "fusion_score": self.fusion_score,
            "source_event_count": len(self.source_events),
            "correlated_item_count": len(self.correlated_items),
            "assessment": self.assessment,
            "classification": self.classification,
            "created_at": self.created_at.isoformat(),
        }


class IntelFusionService:
    """
    Multi-INT fusion engine.

    Accepts raw intelligence events from any source (IMINT, SIGINT, HUMINT,
    CYBER, OSINT) and correlates them spatially, temporally, and by entity.
    When correlation confidence exceeds the threshold the service calls the
    MilitaryBrainService for LLM-powered deep analysis.
    """

    LLM_CONFIDENCE_THRESHOLD = 0.70
    GEO_RADIUS_KM = 10.0          # events within 10 km are considered co-located
    TIME_WINDOW_MINUTES = 60      # default correlation time window

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def fuse_events(self, events: list[dict[str, Any]]) -> FusedIntelligence:
        """
        Fuse a batch of raw intelligence events into a single assessment.

        Steps:
        1. Group by entity / geo cluster
        2. Score fusion confidence based on source diversity and consistency
        3. If score >= threshold, invoke LLM for deep analysis
        4. Persist fusion record
        """
        if not events:
            return FusedIntelligence(
                fusion_id=str(uuid.uuid4()),
                source_events=[],
                entity_id=None,
                fusion_score=0.0,
                correlated_items=[],
                assessment={"status": "NO_DATA"},
                classification="UNCLASSIFIED",
            )

        correlated = self._correlate_by_space_time(events)
        fusion_score = self._calculate_fusion_score(events, correlated)
        entity_id = self._extract_primary_entity(events)
        classification = self._derive_classification(events)

        assessment: dict[str, Any] = {
            "source_count": len(events),
            "correlated_clusters": len(correlated),
            "fusion_score": fusion_score,
            "sources_present": self._list_sources(events),
        }

        if fusion_score >= self.LLM_CONFIDENCE_THRESHOLD:
            logger.info(
                "Fusion score %.2f >= %.2f, invoking ARES for deep analysis",
                fusion_score,
                self.LLM_CONFIDENCE_THRESHOLD,
            )
            llm_assessment = await military_brain.assess_intelligence(events)
            assessment["llm_analysis"] = llm_assessment
            assessment["llm_invoked"] = True
        else:
            assessment["llm_invoked"] = False
            assessment["note"] = (
                f"Fusion score {fusion_score:.2f} below LLM threshold "
                f"{self.LLM_CONFIDENCE_THRESHOLD}. Rule-based assessment only."
            )

        fusion = FusedIntelligence(
            fusion_id=str(uuid.uuid4()),
            source_events=events,
            entity_id=entity_id,
            fusion_score=fusion_score,
            correlated_items=correlated,
            assessment=assessment,
            classification=classification,
        )

        await self._persist_fusion_record(fusion)
        return fusion

    async def correlate_by_entity(
        self,
        entity_id: str,
        time_window_minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """
        Retrieve and correlate all events linked to a specific entity
        within the given time window.
        """
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(
            minutes=time_window_minutes
        )
        stmt = (
            select(Event)
            .where(Event.asset_id == entity_id)
            .where(Event.ts >= cutoff)
            .order_by(desc(Event.ts))
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        correlated: list[dict[str, Any]] = []
        for row in rows:
            correlated.append(
                {
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "asset_id": row.asset_id,
                    "ts": row.ts.isoformat() if row.ts else None,
                    "classification_level": row.classification_level,
                    "confidence_score": row.confidence_score,
                    "payload": row.payload,
                }
            )

        return correlated

    async def generate_intelligence_product(
        self,
        product_type: ProductType,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate a formal intelligence product (INTSUM, SITREP, THREATSUM, etc.)
        and persist it to the database.

        Returns the persisted product as a dict.
        """
        product_id = str(uuid.uuid4())
        content: str

        if product_type == "INTSUM":
            content = await self._generate_intsum(data)
        elif product_type == "SITREP":
            content = await self._generate_sitrep(data)
        elif product_type == "THREATSUM":
            content = await self._generate_threatsum(data)
        elif product_type in ("COA_BRIEF", "STRAT_BRIEF"):
            events = data.get("events", [])
            alerts = data.get("alerts", [])
            content = await military_brain.generate_strategic_briefing(events, alerts)
        else:
            content = f"[UNSUPPORTED PRODUCT TYPE: {product_type}]"

        classification = data.get("classification", "CONFIDENTIAL")
        now = datetime.datetime.utcnow()

        product = IntelligenceProduct(
            id=product_id,
            product_type=product_type,
            content=content,
            classification_level=classification,
            source_data=data,
            created_at=now,
            created_by=data.get("requestor", "SYSTEM"),
        )
        self.db.add(product)
        await self.db.commit()

        return {
            "id": product_id,
            "product_type": product_type,
            "classification": classification,
            "content": content,
            "created_at": now.isoformat(),
        }

    # ------------------------------------------------------------------
    # Internal generators
    # ------------------------------------------------------------------

    async def _generate_intsum(self, data: dict[str, Any]) -> str:
        intel_items = data.get("intel_items", [])
        if not intel_items:
            return "[INTSUM] No intelligence items provided."
        result = await military_brain.assess_intelligence(intel_items)
        if "raw_analysis" in result:
            return result["raw_analysis"]
        return str(result)

    async def _generate_sitrep(self, data: dict[str, Any]) -> str:
        events = data.get("events", [])
        alerts = data.get("alerts", [])
        return await military_brain.generate_strategic_briefing(events, alerts)

    async def _generate_threatsum(self, data: dict[str, Any]) -> str:
        threat_data = data.get("threat_data", {})
        context = data.get("context", {})
        result = await military_brain.analyze_threat(threat_data, context)
        return result.get("raw_analysis", str(result))

    # ------------------------------------------------------------------
    # Correlation logic
    # ------------------------------------------------------------------

    @staticmethod
    def _correlate_by_space_time(
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Group events that are spatially and temporally proximate.
        Returns a flat list of correlation pairs with metadata.
        """
        correlated: list[dict[str, Any]] = []
        n = len(events)
        for i in range(n):
            for j in range(i + 1, n):
                e1, e2 = events[i], events[j]
                geo_close = IntelFusionService._geo_proximity(e1, e2)
                time_close = IntelFusionService._time_proximity(
                    e1, e2, IntelFusionService.TIME_WINDOW_MINUTES
                )
                if geo_close and time_close:
                    correlated.append(
                        {
                            "event_a": e1.get("event_id", e1.get("id")),
                            "event_b": e2.get("event_id", e2.get("id")),
                            "correlation_reason": "GEO+TIME",
                            "sources": [
                                e1.get("source_type", "UNKNOWN"),
                                e2.get("source_type", "UNKNOWN"),
                            ],
                        }
                    )
        return correlated

    @staticmethod
    def _geo_proximity(
        e1: dict[str, Any],
        e2: dict[str, Any],
        radius_km: float = GEO_RADIUS_KM,
    ) -> bool:
        """
        Approximate geo-proximity check using the Haversine formula.
        Returns True if the two events are within radius_km of each other.
        """
        import math

        def _extract_coords(event: dict[str, Any]) -> tuple[float, float] | None:
            loc = event.get("location") or event.get("geo") or {}
            lat = loc.get("lat") or loc.get("latitude")
            lon = loc.get("lon") or loc.get("longitude")
            if lat is None or lon is None:
                return None
            return float(lat), float(lon)

        c1 = _extract_coords(e1)
        c2 = _extract_coords(e2)
        if c1 is None or c2 is None:
            # Cannot determine — assume not co-located
            return False

        lat1, lon1 = c1
        lat2, lon2 = c2

        R = 6371.0  # Earth radius km
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(d_lon / 2) ** 2
        )
        dist = 2 * R * math.asin(math.sqrt(a))
        return dist <= radius_km

    @staticmethod
    def _time_proximity(
        e1: dict[str, Any],
        e2: dict[str, Any],
        window_minutes: int,
    ) -> bool:
        """Return True if the two events occurred within window_minutes of each other."""
        def _parse_ts(event: dict[str, Any]) -> datetime.datetime | None:
            raw = event.get("ts") or event.get("timestamp") or event.get("capture_time")
            if raw is None:
                return None
            if isinstance(raw, datetime.datetime):
                return raw
            try:
                return datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                return None

        t1 = _parse_ts(e1)
        t2 = _parse_ts(e2)
        if t1 is None or t2 is None:
            return True  # Unknown timestamps — assume within window
        delta = abs((t1 - t2).total_seconds())
        return delta <= window_minutes * 60

    @staticmethod
    def _calculate_fusion_score(
        events: list[dict[str, Any]],
        correlated: list[dict[str, Any]],
    ) -> float:
        """
        Heuristic fusion confidence score (0.0 – 1.0).

        Higher score when:
        - More distinct intelligence sources are present (source diversity)
        - High proportion of events are correlated
        - Events carry high individual confidence scores
        """
        if not events:
            return 0.0

        # Source diversity bonus (each unique INT source adds weight)
        sources = {e.get("source_type", "UNKNOWN") for e in events}
        diversity = min(len(sources) / 5.0, 0.40)  # max 0.40 for 5+ sources

        # Correlation ratio
        max_pairs = len(events) * (len(events) - 1) / 2 if len(events) > 1 else 1
        corr_ratio = min(len(correlated) / max(max_pairs, 1), 1.0) * 0.35  # max 0.35

        # Average individual confidence
        confidences = [
            float(e.get("confidence", e.get("confidence_score", 0.5)))
            for e in events
        ]
        avg_confidence = sum(confidences) / len(confidences) * 0.25  # max 0.25

        return round(min(diversity + corr_ratio + avg_confidence, 1.0), 3)

    @staticmethod
    def _list_sources(events: list[dict[str, Any]]) -> list[str]:
        return sorted({e.get("source_type", "UNKNOWN") for e in events})

    @staticmethod
    def _extract_primary_entity(events: list[dict[str, Any]]) -> str | None:
        for event in events:
            eid = event.get("entity_id") or event.get("asset_id") or event.get("emitter_id")
            if eid:
                return str(eid)
        return None

    @staticmethod
    def _derive_classification(events: list[dict[str, Any]]) -> str:
        """Use the highest classification level present in the input events."""
        levels = {
            "UNCLASSIFIED": 0,
            "RESTRICTED": 1,
            "CONFIDENTIAL": 2,
            "SECRET": 3,
            "TOP_SECRET": 4,
        }
        highest = "UNCLASSIFIED"
        for event in events:
            lvl = event.get("classification", event.get("classification_level", "UNCLASSIFIED")).upper()
            if levels.get(lvl, 0) > levels.get(highest, 0):
                highest = lvl
        return highest

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_fusion_record(self, fusion: FusedIntelligence) -> None:
        try:
            record = IntelFusionRecord(
                id=fusion.fusion_id,
                entity_id=fusion.entity_id,
                fusion_score=fusion.fusion_score,
                source_count=len(fusion.source_events),
                correlated_count=len(fusion.correlated_items),
                assessment=fusion.assessment,
                classification_level=fusion.classification,
                created_at=fusion.created_at,
            )
            self.db.add(record)
            await self.db.commit()
        except Exception as exc:
            logger.error("Failed to persist fusion record: %s", exc)
            await self.db.rollback()
