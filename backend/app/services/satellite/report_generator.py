"""IMINT PDF report generator."""
import logging
logger = logging.getLogger(__name__)


def generate_report(analysis: dict, output_path: str) -> str:
    """Generate classified PDF report."""
    logger.info(f"Generating report at {output_path}")
    return output_path
