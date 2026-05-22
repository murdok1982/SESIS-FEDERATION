from pydantic import Field
from pydantic_settings import BaseSettings


class SatelliteSettings(BaseSettings):
    model_config = {"env_prefix": "SAT_", "env_file": ".env", "extra": "ignore"}

    SENTINEL_USER: str = ""
    SENTINEL_PASS: str = ""
    DB_PATH: str = "data/satellite"
    YOLO_MODEL: str = "yolov8n.pt"
    OLLAMA_MODEL: str = "fsociety"
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    FERNET_KEY_PATH: str = "fernet.key"
    MAX_CLOUD_COVER: float = 20.0
    SCAN_INTERVAL_HOURS: int = 6


satellite_settings = SatelliteSettings()
