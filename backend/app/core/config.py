# -*- coding: utf-8 -*-
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import List, Optional
import secrets


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}

    # Environment
    ENVIRONMENT: str = Field(default="development", pattern="^(development|staging|production)$")
    DEBUG: bool = Field(default=True)
    LOG_LEVEL: str = Field(default="DEBUG", pattern="^(DEBUG|INFO|WARNING|ERROR)$")

    # Security
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_hex(32), min_length=32)
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, ge=1, le=60)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=30)
    MFA_ENABLED: bool = Field(default=True)
    FERNET_KEY_PATH: str = Field(default="fernet.key")

    # Database
    DATABASE_URL: str = Field(default="postgresql+asyncpg://sesis:sesis@postgres:5432/sesis")
    REDIS_URL: str = Field(default="redis://redis:6379/0")
    NATS_URL: str = Field(default="nats://nats:4222")

    # Neo4j
    NEO4J_URI: str = Field(default="bolt://neo4j:7687")
    NEO4J_USER: str = Field(default="neo4j")
    NEO4J_PASSWORD: str = Field(default="")

    # LLM / Ollama
    OLLAMA_BASE_URL: str = Field(default="http://ollama:11434")
    OLLAMA_MODEL: str = Field(default="fsociety")
    OLLAMA_TIMEOUT: int = Field(default=120, ge=10, le=300)

    # CORS
    CORS_ORIGINS: str = Field(default="http://localhost:3000,http://localhost:8501")

    # Rate Limiting
    RATE_LIMIT_DEFAULT: int = Field(default=60, ge=1)

    # Monitoring
    GRAFANA_ADMIN_USER: str = Field(default="admin")
    GRAFANA_ADMIN_PASSWORD: str = Field(default="")

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v):
        if v == "change-this-to-a-random-64-char-string":
            raise ValueError("SECRET_KEY must be changed from default in production")
        return v

    @field_validator("NEO4J_PASSWORD")
    @classmethod
    def validate_neo4j_password(cls, v, info):
        if info.data.get("ENVIRONMENT") == "production" and not v:
            raise ValueError("NEO4J_PASSWORD is required in production")
        return v

    @field_validator("GRAFANA_ADMIN_PASSWORD")
    @classmethod
    def validate_grafana_password(cls, v, info):
        if info.data.get("ENVIRONMENT") == "production" and not v:
            raise ValueError("GRAFANA_ADMIN_PASSWORD is required in production")
        return v


settings = Settings()


def get_settings() -> Settings:
    return settings
