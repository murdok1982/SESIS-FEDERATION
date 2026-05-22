"""Sentinel-2 downloader."""
import logging
logger = logging.getLogger(__name__)


def download_scene(lat: float, lon: float, date: str = "latest") -> str:
    """Download Sentinel-2 scene for given coordinates."""
    logger.info(f"Downloading Sentinel-2 scene at {lat},{lon} for {date}")
    return "sentinel_scene.tiff"
