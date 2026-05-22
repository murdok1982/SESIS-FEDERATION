from typing import List, Dict, Any
import datetime

class BriefingGenerator:
    """
    Generates explainable operational briefings based on recent events and alerts.
    """
    
    @staticmethod
    def generate_daily_briefing(assets: List[Dict[str, Any]], events: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> str:
        """
        Produces a text-based briefing summary.
        """
        now = datetime.datetime.utcnow().isoformat()
        
        briefing = f"# SESIS OPERATIONAL BRIEFING - {now}\n\n"
        
        # 1. Asset Status
        active_assets = [a for a in assets if a.get("current_status") == "active"]
        briefing += f"## Asset Status\n"
        briefing += f"- Total Registered Assets: {len(assets)}\n"
        briefing += f"- Currently Active: {len(active_assets)}\n\n"
        
        # 2. Critical Alerts
        critical_alerts = [a for a in alerts if a.get("severity") in ["HIGH", "CRITICAL"]]
        briefing += f"## Critical findings\n"
        if not critical_alerts:
            briefing += "- No high-severity threats detected in the last window.\n"
        else:
            for alert in critical_alerts:
                briefing += f"- **{alert['rule_id']}**: {alert['description']} (Requires Validation)\n"
        
        # 3. Anomaly Summary
        anomalies = [a for a in alerts if a.get("is_anomaly")]
        briefing += f"\n## Intelligence Analysis\n"
        briefing += f"- Detected {len(anomalies)} statistical anomalies in telemetry.\n"
        briefing += f"- Major event types: {', '.join(set(e['event_type'] for e in events[:10]))}\n"
        
        briefing += "\n---\n*Confidential - SESIS Autonomous Agent Output*"
        
        return briefing
