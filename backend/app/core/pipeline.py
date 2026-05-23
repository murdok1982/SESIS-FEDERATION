import asyncio
import logging
from typing import Callable, Dict, Any, List
from app.core.events import EventBus

logger = logging.getLogger(__name__)

PIPELINE_EVENTS = {
    "satellite.detection": {"emitter": "satellite", "subscribers": ["osint", "c2", "agents"]},
    "osint.intel_update": {"emitter": "osint", "subscribers": ["intel", "c2"]},
    "intel.threat_assessment": {"emitter": "intel", "subscribers": ["c2", "agents", "ml"]},
    "agents.field_report": {"emitter": "agents", "subscribers": ["intel", "c2", "ml"]},
    "c2.mission_order": {"emitter": "c2", "subscribers": ["agents", "satellite", "intel"]},
    "ml.correlation_alert": {"emitter": "ml", "subscribers": ["c2", "intel"]},
}


class FusionPipeline:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.handlers: Dict[str, List[Callable]] = {}
        self._running = False

    async def subscribe_all(self):
        for event_type, config in PIPELINE_EVENTS.items():
            async def make_handler(et=event_type):
                async def handler(data):
                    await self._route_event(et, data)
                return handler
            h = await make_handler()
            await self.event_bus.subscribe(event_type, h)
            logger.info(f"Pipeline subscribed to {event_type}")
        self._running = True

    async def _route_event(self, event_type: str, data: Dict[str, Any]):
        for attempt in range(3):
            try:
                for handler in self.handlers.get(event_type, []):
                    await handler(data)
                return
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"Pipeline routing failed for {event_type}: {e}")

    def register_handler(self, event_type: str, handler: Callable):
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)


class ModuleRouter:
    def __init__(self, pipeline: FusionPipeline):
        self.pipeline = pipeline

    async def route_to_osint(self, data: dict):
        logger.info(f"Routing satellite detection to OSINT: {data.get('coordinates')}")
        await self.pipeline.event_bus.publish("osint.cross_ref", {"source": "satellite", "data": data})

    async def route_to_intel(self, data: dict):
        logger.info(f"Routing OSINT update to Intel: {data.get('summary', '')[:50]}")
        await self.pipeline.event_bus.publish("intel.analyze", {"source": "osint", "data": data})

    async def route_to_c2(self, data: dict):
        logger.info(f"Routing threat to C2: severity={data.get('severity')}")
        await self.pipeline.event_bus.publish("c2.alert", {"source": "intel", "data": data})

    async def route_to_agents(self, data: dict):
        logger.info(f"Routing C2 order to agents")
        await self.pipeline.event_bus.publish("agents.mission", {"source": "c2", "data": data})
