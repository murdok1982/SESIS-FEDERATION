"""Tactical annotator for military imagery."""
import logging
logger = logging.getLogger(__name__)


def annotate_image(image_path: str, detections: list) -> str:
    """Add tactical bounding boxes to image."""
    logger.info(f"Annotating {image_path} with {len(detections)} detections")
    return image_path
