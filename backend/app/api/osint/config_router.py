from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.osint.deps import *
from app.core.config import settings

router = APIRouter()

@router.get("/providers")
async def list_providers(user: CurrentUser) -> dict:
    providers = [
        {
            "name": "ollama",
            "available": True,
            "models": [settings.OLLAMA_DEFAULT_MODEL],
            "default_model": settings.OLLAMA_DEFAULT_MODEL,
            "requires_key": False,
        }
    ]
    for name, key, model in [
        ("openai", settings.OPENAI_API_KEY, settings.OPENAI_DEFAULT_MODEL),
        ("anthropic", settings.ANTHROPIC_API_KEY, settings.ANTHROPIC_DEFAULT_MODEL),
        ("openrouter", settings.OPENROUTER_API_KEY, settings.OPENROUTER_DEFAULT_MODEL),
    ]:
        providers.append({
            "name": name,
            "available": bool(key),
            "models": [model] if key else [],
            "default_model": model,
            "requires_key": True,
        })

    fallback = [p["name"] for p in providers if p["available"]]
    return {
        "providers": providers,
        "active_provider": settings.LLM_DEFAULT_PROVIDER,
        "fallback_chain": fallback,
    }

@router.get("/integrations")
async def list_integrations(user: CurrentUser) -> dict:
    return {
        "shodan": bool(settings.SHODAN_API_KEY),
        "virustotal": bool(settings.VIRUSTOTAL_API_KEY),
        "hunter_io": bool(settings.HUNTER_IO_API_KEY),
        "urlscan": bool(settings.URLSCAN_API_KEY),
        "ipinfo": bool(settings.IPINFO_TOKEN),
        "securitytrails": bool(settings.SECURITYTRAILS_API_KEY),
        "hibp": bool(settings.HIBP_API_KEY),
    }

@router.get("/system")
async def get_system_config(user: Annotated[object, Depends(require_admin)]) -> dict:
    return {
        "environment": settings.ENVIRONMENT,
        "log_level": settings.LOG_LEVEL,
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
        "rate_limit_per_minute": settings.RATE_LIMIT_PER_MINUTE,
        "evidence_storage_path": settings.EVIDENCE_STORAGE_PATH,
        "reports_storage_path": settings.REPORTS_STORAGE_PATH,
        "telegram_allowed_chats": len(settings.TELEGRAM_ALLOWED_CHATS),
    }
