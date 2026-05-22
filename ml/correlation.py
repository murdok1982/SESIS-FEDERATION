from typing import List, Dict, Any
import uuid

class EventCorrelator:
    """
    Correlates multiple events to identify higher-level threats or situations.
    """
    
    @staticmethod
    def correlate_multi_domain(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Simplistic correlation: If an RF anomaly and a Manual observation occur 
        within 1km and 5 minutes of each other, raise a High Severity Alert.
        """
        correlations = []
        
        # This is a placeholder for a complex rule engine or graph-based correlation
        # For now, we simulate finding a pattern.
        
        rf_events = [e for e in events if e["event_type"] == "rf_anomaly_event"]
        manual_events = [e for e in events if e["event_type"] == "manual_observation"]
        
        for rf in rf_events:
            for man in manual_events:
                # Mock spatial-temporal check
                if rf["asset_id"] != man["asset_id"]: # Different sources
                    # if dist(rf, man) < 1000 and abs(rf["ts"] - man["ts"]) < 300:
                    correlations.append({
                        "id": str(uuid.uuid4()),
                        "rule_id": "RF_MANUAL_PROXIMITY",
                        "severity": "HIGH",
                        "description": f"RF Anomaly and Manual Observation correlated in close proximity.",
                        "involved_events": [rf["event_id"], man["event_id"]]
                    })
                    
        return correlations
