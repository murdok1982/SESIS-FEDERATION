"""Shodan integration wrapper (requires SHODAN_API_KEY)."""
from __future__ import annotations

import httpx
from app.core.config import get_settings

class ShodanWrapper:
    BASE = "https://api.shodan.io"

    def __init__(self) -> None:
        settings = get_settings()
        self.key = settings.SHODAN_API_KEY
        if not self.key:
            raise RuntimeError("SHODAN_API_KEY not configured")

    async def host_info(self, ip: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.BASE}/shodan/host/{ip}", params={"key": self.key})
            r.raise_for_status()
            return r.json()

    async def search(self, query: str, page: int = 1) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.BASE}/shodan/host/search", params={"key": self.key, "query": query, "page": page})
            r.raise_for_status()
            return r.json()

    async def domain_info(self, domain: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.BASE}/dns/domain/{domain}", params={"key": self.key})
            r.raise_for_status()
            return r.json()
