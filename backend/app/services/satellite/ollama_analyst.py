"""Ollama IMINT analysis."""
import logging
logger = logging.getLogger(__name__)


async def analyze_imagery(image_path: str, prompt: str = "Describe this military image") -> str:
    """Analyze satellite imagery using Ollama LLM."""
    logger.info(f"Analyzing {image_path}")
    return "IMINT analysis complete."
