"""SIEM integration service."""
import logging
logger = logging.getLogger(__name__)


class SIEMService:
    async def forward_event(self, event: dict) -> bool:
        logger.info(f"Forwarding event to SIEM")
        return True
