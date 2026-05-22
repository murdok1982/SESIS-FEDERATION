"""VirusTotal integration wrapper (requires VIRUSTOTAL_API_KEY)."""
from __future__ import annotations

import httpx
from app.core.config import get_settings

class VirusTotalWrapper:
    BASE = "https://www.virustotal.com/api/v3"

    def __init__(self) -> None:
        settings = get_settings()
        self.key = settings.VIRUSTOTAL_API_KEY
        if not self.key:
            raise RuntimeError("VIRUSTOTAL_API_KEY not configured")
        self.headers = {"x-apikey": self.key}

    async def file_report(self, sha256: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.BASE}/files/{sha256}", headers=self.headers)
            r.raise_for_status()
            return r.json()

    async def url_scan(self, url: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{self.BASE}/urls", headers=self.headers, data={"url": url})
            r.raise_for_status()
            return r.json()

    async def domain_report(self, domain: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.BASE}/domains/{domain}", headers=self.headers)
            r.raise_for_status()
            return r.json()

    async def ip_report(self, ip: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.BASE}/ip_addresses/{ip}", headers=self.headers)
            r.raise_for_status()
            return r.json()
