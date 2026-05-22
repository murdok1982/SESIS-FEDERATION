"""Hunter.io integration wrapper (requires HUNTER_API_KEY)."""
from __future__ import annotations

import httpx
from app.core.config import get_settings

class HunterWrapper:
    BASE = "https://api.hunter.io/v2"

    def __init__(self) -> None:
        settings = get_settings()
        self.key = settings.HUNTER_API_KEY
        if not self.key:
            raise RuntimeError("HUNTER_API_KEY not configured")

    async def domain_search(self, domain: str, limit: int = 10) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.BASE}/domain-search", params={"domain": domain, "limit": limit, "api_key": self.key})
            r.raise_for_status()
            return r.json()

    async def email_finder(self, domain: str, first_name: str, last_name: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.BASE}/email-finder", params={"domain": domain, "first_name": first_name, "last_name": last_name, "api_key": self.key})
            r.raise_for_status()
            return r.json()

    async def email_verifier(self, email: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.BASE}/email-verifier", params={"email": email, "api_key": self.key})
            r.raise_for_status()
            return r.json()
