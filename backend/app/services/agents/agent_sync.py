"""Agent synchronization service."""
import logging
logger = logging.getLogger(__name__)


class AgentSyncService:
    async def sync_agent(self, agent_id: str, data: dict) -> bool:
        logger.info(f"Syncing agent {agent_id}")
        return True
