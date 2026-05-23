import random
from typing import Dict, Any, List


class WargamingSimulator:
    """Simulador de Cursos de Accion para wargaming tactico."""

    async def simulate_coa(self, coa: Dict, scenario: Dict) -> Dict:
        success_prob = random.uniform(0.3, 0.9)
        return {
            "coa": coa.get("name", "unnamed"),
            "success_probability": round(success_prob, 2),
            "estimated_casualties": random.randint(1, 50),
            "estimated_duration_hours": random.randint(2, 72),
            "risks": ["enemy reserves", "weather", "logistics"] if success_prob < 0.6 else [],
        }

    async def compare_coas(self, coas: List[Dict], scenario: Dict) -> List[Dict]:
        results = []
        for coa in coas:
            result = await self.simulate_coa(coa, scenario)
            results.append(result)
        return sorted(results, key=lambda x: x["success_probability"], reverse=True)

    async def monte_carlo(self, coa: Dict, iterations: int = 1000) -> Dict:
        wins = 0
        for _ in range(iterations):
            if random.random() < 0.65:
                wins += 1
        return {
            "coa": coa.get("name", "unnamed"),
            "iterations": iterations,
            "win_rate": round(wins / iterations, 3),
            "recommendation": "viable" if (wins / iterations) > 0.5 else "not_recommended",
        }


wargaming = WargamingSimulator()
