# -*- coding: utf-8 -*-
import json
import logging
from typing import Callable, Dict, Any, Optional

logger = logging.getLogger(__name__)


class EventBus:
    """Unified event bus using NATS for C2/telemetry messaging."""

    def __init__(self):
        self.nc = None
        self.js = None
        self.subscribers: Dict[str, list] = {}

    async def connect(self):
        try:
            import nats
            from app.core.config import settings
            self.nc = await nats.connect(settings.NATS_URL)
            self.js = self.nc.jetstream()
            logger.info(f"Connected to NATS at {settings.NATS_URL}")
        except ImportError:
            logger.warning("nats-py not installed — using in-memory event bus")
        except Exception as e:
            logger.error(f"NATS connection failed: {e}")

    async def disconnect(self):
        if self.nc:
            await self.nc.drain()
            self.nc = None

    async def publish(self, subject: str, data: Dict[str, Any]):
        if self.nc:
            await self.nc.publish(subject, json.dumps(data).encode())
        for cb in self.subscribers.get(subject, []):
            await cb(data)

    async def subscribe(self, subject: str, callback: Callable):
        if subject not in self.subscribers:
            self.subscribers[subject] = []
        self.subscribers[subject].append(callback)
        if self.nc:
            await self.nc.subscribe(subject, cb=lambda msg: callback(json.loads(msg.data)))


event_bus = EventBus()
