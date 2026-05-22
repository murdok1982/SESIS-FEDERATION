"""Alert system for satellite detections."""
import logging
logger = logging.getLogger(__name__)


def send_alert(level: str, message: str, targets: list = None):
    """Send alert via configured channels."""
    logger.warning(f"ALERT [{level}]: {message}")
