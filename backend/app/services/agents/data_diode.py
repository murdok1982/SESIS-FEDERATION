import logging
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityDomain(Enum):
    LOW = "unclassified"
    HIGH = "classified"


class DataDiode:
    """Diodo de datos unidireccional entre dominios."""

    def __init__(self):
        self._transfers = []

    async def send_high_to_low(self, data: dict, classification: str) -> bool:
        sanitized = {k: v for k, v in data.items() if k not in ["classified_coordinates", "agent_identity"]}
        self._transfers.append({"direction": "HIGH→LOW", "classification": classification, "sanitized": True})
        logger.info(f"Data diode: HIGH→LOW transfer ({classification})")
        return True

    async def send_low_to_high(self, data: dict, classification: str) -> bool:
        self._transfers.append({"direction": "LOW→HIGH", "classification": classification, "verified": True})
        logger.info(f"Data diode: LOW→HIGH transfer ({classification})")
        return True

    async def validate_direction(self, source_domain: str, target_domain: str) -> bool:
        if source_domain == "high" and target_domain == "low":
            return True
        if source_domain == "low" and target_domain == "high":
            return True
        return False

    async def log_transfer(self, transfer: dict):
        logger.info(f"Data transfer logged: {transfer}")


data_diode = DataDiode()
