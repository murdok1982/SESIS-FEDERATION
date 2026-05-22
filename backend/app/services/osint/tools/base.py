from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

@dataclass
class ToolResult:
    success: bool
    data: Any
    source: str
    method: str
    error: str | None = None
    cached: bool = False
    duration_ms: float = 0.0

class ToolBase:
    name: str = ""
    description: str = ""
    rate_limit_per_minute: int = 60
    _call_times: list[float]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Each subclass gets its own call_times list
        cls._call_times = []

    async def execute(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError

    async def _rate_limit_check(self) -> None:
        now = time.monotonic()
        self._call_times = [t for t in self._call_times if now - t < 60.0]
        if len(self._call_times) >= self.rate_limit_per_minute:
            import asyncio  # noqa: PLC0415
            sleep_time = 60.0 - (now - self._call_times[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        self._call_times.append(time.monotonic())

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolBase] = {}

    def register(self, tool: ToolBase) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolBase | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

def build_default_registry(config: Any) -> ToolRegistry:
    from app.services.osint.tools.dns_tools import DnsLookupTool  # noqa: PLC0415
    from app.services.osint.tools.whois_tools import WhoisTool  # noqa: PLC0415
    from app.services.osint.tools.web_tools import WebFetchTool, WebSearchTool, IpGeolocationTool  # noqa: PLC0415
    from app.services.osint.tools.cert_tools import CertSearchTool  # noqa: PLC0415
    from app.services.osint.tools.social_tools import SocialProfileFetchTool  # noqa: PLC0415
    from app.services.osint.tools.document_tools import DocumentExtractTool  # noqa: PLC0415
    from app.services.osint.tools.archive_tools import ArchiveLookupTool  # noqa: PLC0415

    registry = ToolRegistry()
    for tool in [
        DnsLookupTool(), WhoisTool(), WebFetchTool(config), WebSearchTool(),
        IpGeolocationTool(config), CertSearchTool(), SocialProfileFetchTool(),
        DocumentExtractTool(config), ArchiveLookupTool(),
    ]:
        registry.register(tool)
    return registry
