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
from app.api.satellite.router import router as satellite_router
app.include_router(satellite_router, prefix="/api/v1/satellite", tags=["Satellite", "AEGIS-IMINT"])

# sesis-osint (from Atalaya)
from app.api.osint.router import router as osint_router
app.include_router(osint_router, prefix="/api/v1/osint", tags=["OSINT", "Atalaya"])

# sesis-intel (from Global-Intelligence)
from app.api.intel.router import router as intel_router
app.include_router(intel_router, prefix="/api/v1/intel", tags=["Intelligence", "Global-Intel"])

# sesis-agents (from SpyManager)
from app.api.agents.router import router as agents_router
app.include_router(agents_router, prefix="/api/v1/agents", tags=["Agents", "SpyManager"])

# Extra agent API modules
from app.api.agents import intel_api, mesh_api, mobile_api, multimodal_api, steganography_api, threat_api, wearable_api
app.include_router(intel_api.router, prefix="/api/v1/agents/intel", tags=["Agents", "Intel"])
app.include_router(mesh_api.router, prefix="/api/v1/agents/mesh", tags=["Agents", "Mesh"])
app.include_router(mobile_api.router, prefix="/api/v1/agents/mobile", tags=["Agents", "Mobile"])
app.include_router(multimodal_api.router, prefix="/api/v1/agents/multimodal", tags=["Agents", "Multimodal"])
app.include_router(steganography_api.router, prefix="/api/v1/agents/stego", tags=["Agents", "Steganography"])
app.include_router(threat_api.router, prefix="/api/v1/agents/threat", tags=["Agents", "Threat"])
app.include_router(wearable_api.router, prefix="/api/v1/agents/wearable", tags=["Agents", "Wearable"])

# sesis-tactical (OPORD, Wargaming, Joint Fires, BDA, PSYOPS)
from app.api.tactical import opord, wargaming, joint_fires, bda, psyops
app.include_router(opord.router, prefix="/api/v1/tactical/opord", tags=["Tactical", "OPORD"])
app.include_router(wargaming.router, prefix="/api/v1/tactical/wargaming", tags=["Tactical", "Wargaming"])
app.include_router(joint_fires.router, prefix="/api/v1/tactical/fires", tags=["Tactical", "Joint Fires"])
app.include_router(bda.router, prefix="/api/v1/tactical/bda", tags=["Tactical", "BDA"])
app.include_router(psyops.router, prefix="/api/v1/tactical/psyops", tags=["Tactical", "PSYOPS"])

# sesis-sensors (IoT Mesh)
from app.api.agents import sensor_mesh_api
app.include_router(sensor_mesh_api.router, prefix="/api/v1/agents/sensors", tags=["Agents", "Sensors"])

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
