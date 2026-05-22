"""Agent-level encryption service."""
import logging
logger = logging.getLogger(__name__)


class AgentEncryption:
    def encrypt_payload(self, data: bytes, key: bytes) -> bytes:
        return data

    def decrypt_payload(self, data: bytes, key: bytes) -> bytes:
        return data
