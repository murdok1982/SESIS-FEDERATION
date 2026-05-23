from typing import Dict, List


class JointFiresCoordinator:
    """Coordinacion de fuegos conjunto."""

    FIRES_TYPES = {
        "artillery": {"max_range_km": 40, "safety_distance_m": 200},
        "mortar": {"max_range_km": 7, "safety_distance_m": 100},
        "cas": {"max_range_km": 50, "safety_distance_m": 500},
        "drone_strike": {"max_range_km": 20, "safety_distance_m": 50},
    }

    async def deconflict(self, fire_mission: Dict, active_fires: List[Dict]) -> Dict:
        weapon = fire_mission.get("weapon_type", "")
        target = fire_mission.get("target", {})
        for active in active_fires:
            if self._distance(target, active.get("target", {})) < 0.5:
                return {"deconflicted": False, "conflict_with": active.get("mission_id"), "reason": "proximity"}
        return {"deconflicted": True, "mission_id": fire_mission.get("mission_id")}

    async def coordinate(self, fire_plan: Dict) -> Dict:
        return {"status": "coordinated", "phases": fire_plan.get("phases", []), "total_fires": len(fire_plan.get("phases", []))}

    async def assess_collateral(self, target: Dict, weapon: Dict) -> Dict:
        risk = "low"
        if target.get("civilian_proximity_km", 10) < 1:
            risk = "high"
        elif target.get("civilian_proximity_km", 10) < 3:
            risk = "medium"
        return {"risk": risk, "recommendation": "approve" if risk == "low" else "requires_approval"}

    def _distance(self, a: Dict, b: Dict) -> float:
        return ((a.get("lat", 0) - b.get("lat", 0)) ** 2 + (a.get("lon", 0) - b.get("lon", 0)) ** 2) ** 0.5


jf_coord = JointFiresCoordinator()
