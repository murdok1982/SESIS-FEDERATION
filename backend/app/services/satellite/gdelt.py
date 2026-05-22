"""GDELT event cross-referencing."""
import logging
logger = logging.getLogger(__name__)


def cross_reference(lat: float, lon: float, radius_km: float = 50) -> list:
    """Cross-reference coordinates with GDELT events."""
    logger.info(f"Cross-referencing {lat},{lon}")
    return []
