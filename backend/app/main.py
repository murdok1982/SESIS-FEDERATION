# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings, get_settings
from app.db.session import engine, check_db_connected
from app.core.events import EventBus

logger = logging.getLogger(__name__)
event_bus = EventBus()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SESIS-FEDERATION...")

    # Database
    await check_db_connected()
    logger.info("Database connected")

    # Redis with retry
    redis_ok = False
    for attempt in range(5):
        try:
            from app.db.redis_pool import get_redis_pool
            r = await get_redis_pool()
            await r.ping()
            redis_ok = True
            logger.info("Redis connected")
            break
        except Exception as e:
            if attempt < 4:
                await asyncio.sleep(2 * (2 ** attempt))
                logger.warning(f"Redis retry {attempt + 1}: {e}")
            else:
                logger.warning(f"Redis unavailable after 5 retries: {e}")

    # NATS
    try:
        await event_bus.connect()
        logger.info("NATS connected")
    except Exception as e:
        logger.warning(f"NATS unavailable: {e}")

    # Init DB schema
    from app.db.init_db import init_db
    await asyncio.to_thread(init_db, settings)

    yield

    await event_bus.disconnect()
    await engine.dispose()
    logger.info("SESIS-FEDERATION stopped")


app = FastAPI(
    title="SESIS-FEDERATION",
    description="Plataforma Unificada de Gobierno Digital Militar — C4ISR",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.ENVIRONMENT == "production":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["api.sesis.local"])

# ── Module Routers ──

# sesis-core
from app.api.health import router as health_router
app.include_router(health_router, prefix="/api/v1", tags=["Health"])

# sesis-c2 (from SESIS)
from app.api.v1 import alerts, assets, intel, ingestion, sensors, timeline, brain
app.include_router(alerts.router, prefix="/api/v1/c2", tags=["C2"])
app.include_router(assets.router, prefix="/api/v1/c2", tags=["C2"])
app.include_router(intel.router, prefix="/api/v1/c2", tags=["C2"])
app.include_router(ingestion.router, prefix="/api/v1/c2", tags=["C2"])
app.include_router(sensors.router, prefix="/api/v1/c2", tags=["C2"])
app.include_router(timeline.router, prefix="/api/v1/c2", tags=["C2"])
app.include_router(brain.router, prefix="/api/v1/c2", tags=["C2"])

# sesis-c2 v2 (border, cyber, ew, logistics, space)
from app.api.v2 import border, cyber, ew, logistics, space, c2
app.include_router(border.router, prefix="/api/v2/border", tags=["Border"])
app.include_router(cyber.router, prefix="/api/v2/cyber", tags=["Cyber"])
app.include_router(ew.router, prefix="/api/v2/ew", tags=["EW"])
app.include_router(logistics.router, prefix="/api/v2/logistics", tags=["Logistics"])
app.include_router(space.router, prefix="/api/v2/space", tags=["Space"])
app.include_router(c2.router, prefix="/api/v2/c2", tags=["C2 v2"])

# sesis-satellite (from AEGIS-IMINT)
try:
    from app.api.satellite import router as satellite_router
    app.include_router(satellite_router, prefix="/api/v1/satellite", tags=["Satellite"])
except ImportError:
    logger.warning("Satellite module not available")

# sesis-osint (from Atalaya)
try:
    from app.api.osint import router as osint_router
    app.include_router(osint_router, prefix="/api/v1/osint", tags=["OSINT"])
except ImportError:
    logger.warning("OSINT module not available")

# sesis-intel (from Global-Intelligence)
try:
    from app.api.intel import router as intel_router
    app.include_router(intel_router, prefix="/api/v1/intel", tags=["Intelligence"])
except ImportError:
    logger.warning("Intel module not available")

# sesis-agents (from SpyManager)
try:
    from app.api.agents import router as agents_router
    app.include_router(agents_router, prefix="/api/v1/agents", tags=["Agents"])
except ImportError:
    logger.warning("Agents module not available")

# sesis-auth (unified)
from app.api.auth import router as auth_router
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])


@app.get("/")
async def root():
    return {
        "service": "SESIS-FEDERATION",
        "version": "1.0.0",
        "status": "operational",
        "environment": settings.ENVIRONMENT,
        "llm": settings.OLLAMA_MODEL,
    }
