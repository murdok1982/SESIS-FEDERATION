"""Intel agents package (migrated from Global-Intelligence)."""

from app.agents.intel.orchestrator import OpenClawOrchestrator, openclaw_master
from app.agents.intel.osint import OSINTAgent
from app.agents.intel.scenario import ScenarioAgent, ContributorIntakeAgent
from app.agents.intel.synthesis import SynthesisAgent, synthesis_agent

__all__ = [
    "OpenClawOrchestrator", "openclaw_master",
    "OSINTAgent",
    "ScenarioAgent", "ContributorIntakeAgent",
    "SynthesisAgent", "synthesis_agent",
]
