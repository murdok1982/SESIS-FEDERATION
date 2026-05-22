"""Watchdog scheduler for automatic scanning."""
import logging
logger = logging.getLogger(__name__)


class WatchdogScheduler:
    def start(self):
        logger.info("Satellite watchdog scheduler started")

    def stop(self):
        logger.info("Satellite watchdog scheduler stopped")

    def add_zone(self, name: str, lat: float, lon: float, interval_hours: int = 6):
        logger.info(f"Added watch zone {name} at {lat},{lon} every {interval_hours}h")
