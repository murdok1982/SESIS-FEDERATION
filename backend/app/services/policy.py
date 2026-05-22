from typing import Dict, Any

class PolicyEvaluator:
    """
    ABAC (Attribute-Based Access Control) Evaluator for SESIS.
    Evaluates Subject, Resource, and Context against defined policies.
    """
    
    @staticmethod
    def evaluate(subject: Dict[str, Any], resource: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decision logic:
        1. Subject clearance MUST be >= Resource classification.
        2. Contextual rules (e.g., mission ID match) must pass.
        """
        
        clearance_levels = {"OPEN": 0, "RESTRICTED": 1, "CONFIDENTIAL": 2, "SECRET": 3, "TOP_SECRET": 4}
        
        subject_clearance = clearance_levels.get(subject.get("clearance", "OPEN"), 0)
        resource_classification = clearance_levels.get(resource.get("classification", "OPEN"), 0)
        
        if subject_clearance < resource_classification:
            return {"decision": "DENY", "reason": "INSUFFICIENT_CLEARANCE"}
            
        # Example contextual rule: Offensive actions require special role
        if resource.get("type") == "OFFENSIVE_ACTION":
            if "OFFENSIVE_OPERATOR" not in subject.get("roles", []):
                return {"decision": "DENY", "reason": "MISSING_OFFENSIVE_ROLE"}
        
        return {"decision": "PERMIT", "reason": "POLICY_MATCH"}
