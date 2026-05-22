"""Change detection between satellite images."""
import logging
logger = logging.getLogger(__name__)


def detect_changes(before: str, after: str) -> dict:
    """Detect changes between two satellite images."""
    logger.info(f"Comparing {before} vs {after}")
    return {"changes": [], "areas_of_interest": []}
