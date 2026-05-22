"""STANAG 5516 / Link 16 integration."""
import logging
logger = logging.getLogger(__name__)


class Link16Service:
    async def send_message(self, message: dict) -> bool:
        logger.info(f"Sending Link 16 message")
        return True
