"""Digital watermarking service."""
import logging
logger = logging.getLogger(__name__)


class WatermarkService:
    def embed_watermark(self, content: bytes, agent_id: str) -> bytes:
        return content

    def verify_watermark(self, content: bytes) -> dict:
        return {"agent_id": None, "verified": False}
