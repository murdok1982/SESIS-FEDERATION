from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.api.osint.deps import *

router = APIRouter()
_start_time = time.time()

@router.get("")
async def health(db: DBSession, redis: RedisConn) -> dict:
    db_ok = False
    redis_ok = False

    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    try:
        await redis.ping()
        redis_ok = True
    except Exception:
        pass

    overall = "ok" if db_ok and redis_ok else "degraded"
    return {
        "status": overall,
        "db": db_ok,
        "redis": redis_ok,
        "version": "0.1.0",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }

@router.get("/detailed")
async def health_detailed(
    db: DBSession,
    redis: RedisConn,
    user: Annotated[object, Depends(require_admin)],
) -> dict:
    from app.core.config import settings  # noqa: PLC0415

    return {
        "environment": settings.ENVIRONMENT,
        "llm_provider": settings.LLM_DEFAULT_PROVIDER,
        "llm_model": settings.LLM_DEFAULT_MODEL,
        "qdrant_url": settings.QDRANT_URL,
        "telegram_configured": bool(settings.TELEGRAM_BOT_TOKEN),
        "allowed_origins": settings.CORS_ORIGINS,
    }

@router.get("/modules")
async def health_modules() -> dict:
    return {
        "osint": {"status": "operational", "last_check": time.time()},
        "socmint": {"status": "not_implemented", "reason": "Pending MVP integration"},
        "imint": {"status": "not_implemented", "reason": "Pending MVP integration"},
        "finint": {"status": "not_implemented", "reason": "Pending MVP integration"},
        "darkweb": {"status": "not_implemented", "reason": "Pending MVP integration"}
    }
