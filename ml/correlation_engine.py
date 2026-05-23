import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from ml import ml_logger

logger = logging.getLogger(__name__)

_RULES_DIR = Path(__file__).parent / "rules"


class CorrelationEngine:
    def __init__(self):
        self.rules = []
        self._load_rules()

    def _load_rules(self):
        if _RULES_DIR.exists():
            for f in _RULES_DIR.glob("*.json"):
                try:
                    with open(f) as fp:
                        data = json.load(fp)
                        if isinstance(data, list):
                            self.rules.extend(data)
                        else:
                            self.rules.append(data)
                    logger.info(f"Loaded {len(self.rules)} correlation rules from {f.name}")
                except Exception as e:
                    logger.error(f"Error loading {f}: {e}")

    async def evaluate(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        matches = []
        for rule in self.rules:
            score = self._match_rule(rule, event)
            if score > 0:
                matches.append({"rule": rule["name"], "confidence": score, "action": rule.get("action")})
        return matches

    def _match_rule(self, rule: Dict, event: Dict) -> float:
        conditions = rule.get("conditions", {})
        if not conditions:
            return 0.0
        matched = 0
        total = len(conditions)
        for key, condition in conditions.items():
            value = event
            for part in key.split("."):
                value = value.get(part, {}) if isinstance(value, dict) else None
            if value is None:
                continue
            if isinstance(condition, bool):
                if value == condition:
                    matched += 1
            elif isinstance(condition, dict):
                for op, target in condition.items():
                    if op == ">=" and isinstance(value, (int, float)) and value >= target:
                        matched += 1
                    elif op == ">" and isinstance(value, (int, float)) and value > target:
                        matched += 1
                    elif op == "<=" and isinstance(value, (int, float)) and value <= target:
                        matched += 1
                    elif op == "<" and isinstance(value, (int, float)) and value < target:
                        matched += 1
            elif value == condition:
                matched += 1
        return matched / total if total > 0 else 0.0


correlation_engine = CorrelationEngine()
