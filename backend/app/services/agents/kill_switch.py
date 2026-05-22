"""Remote wipe and kill switch service."""
import logging
logger = logging.getLogger(__name__)


class KillSwitchService:
    async def activate(self, agent_id: str, reason: str) -> bool:
        logger.warning(f"KILL SWITCH activated for {agent_id}: {reason}")
        return True

    async def deactivate(self, agent_id: str) -> bool:
        logger.info(f"Kill switch deactivated for {agent_id}")
        return True
