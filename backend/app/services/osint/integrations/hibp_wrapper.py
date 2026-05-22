"""Have I Been Pwned integration wrapper (requires HIBP_API_KEY)."""
from __future__ import annotations

import httpx
from app.core.config import get_settings

class HIBPWrapper:
    BASE = "https://haveibeenpwned.com/api/v3"

    def __init__(self) -> None:
        settings = get_settings()
        self.key = settings.HIBP_API_KEY
        if not self.key:
            raise RuntimeError("HIBP_API_KEY not configured")
        self.headers = {"hibp-api-key": self.key, "user-agent": "Atalaya-OSINT/1.0"}

    async def breaches_for_account(self, email: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.BASE}/breachedaccount/{email}", headers=self.headers, params={"truncateResponse": "false"})
            if r.status_code == 404:
                return []
            r.raise_for_status()
            return r.json()

    async def pastes_for_account(self, email: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.BASE}/pasteaccount/{email}", headers=self.headers)
            if r.status_code == 404:
                return []
            r.raise_for_status()
            return r.json()
