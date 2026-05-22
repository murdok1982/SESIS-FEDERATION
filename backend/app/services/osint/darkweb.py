from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings, get_settings

logger = get_logger(__name__)

@dataclass
class DarkWebResult:
    source: str
    url: str
    title: str
    content_snippet: str
    found_keywords: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    timestamp: str = ""

class DarkWebModule:
    """Dark web monitoring and intelligence module."""

    RISK_KEYWORDS = [
        "exploit", "malware", "ransomware", "zero-day", "0day",
        "credentials", "database", "breach", "leaked", "stolen",
        "weapon", "explosive", "trafficking", "illegal", "blackmarket",
    ]

    def __init__(self, tor_proxy: str = "") -> None:
        self._tor_proxy = tor_proxy
        self._monitored_targets: list[str] = []
        self._monitored_keywords: list[str] = []

    def add_target(self, target: str) -> None:
        if target not in self._monitored_targets:
            self._monitored_targets.append(target)
            logger.info("darkweb_target_added", target=target)

    def add_keyword(self, keyword: str) -> None:
        if keyword not in self._monitored_keywords:
            self._monitored_keywords.append(keyword)
            logger.info("darkweb_keyword_added", keyword=keyword)

    async def scan_paste_sites(self, query: str) -> list[DarkWebResult]:
        results = []
        paste_sources = [
            {"name": "Pastebin", "url": "https://pastebin.com"},
            {"name": "Ghostbin", "url": "https://ghostbin.co"},
            {"name": "Paste.ee", "url": "https://paste.ee"},
            {"name": "Rentry.co", "url": "https://rentry.co"},
        ]
        for source in paste_sources:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{source['url']}/search", params={"q": query})
                    if resp.status_code == 200:
                        content = resp.text[:2000]
                        risk = self._calculate_risk(content)
                        results.append(DarkWebResult(
                            source=source["name"],
                            url=f"{source['url']}/search?q={query}",
                            title=f"Search results for {query}",
                            content_snippet=content[:500],
                            found_keywords=self._find_keywords(content),
                            risk_score=risk,
                        ))
            except Exception as exc:
                logger.warning("paste_scan_failed", source=source["name"], error=str(exc))
        return results

    async def scan_breach_databases(self, email: str) -> list[DarkWebResult]:
        results = []
        if email:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(
                        f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}",
                        headers={"hibp-api-key": ""},
                    )
                    if resp.status_code == 200:
                        breaches = resp.json()
                        for breach in breaches:
                            results.append(DarkWebResult(
                                source="HIBP",
                                url=f"https://haveibeenpwned.com/account/{email}",
                                title=breach.get("Name", "Unknown"),
                                content_snippet=breach.get("Description", ""),
                                risk_score=8.0 if breach.get("IsSensitive") else 5.0,
                                timestamp=breach.get("BreachDate", ""),
                            ))
            except Exception as exc:
                logger.warning("breach_scan_failed", email=email, error=str(exc))
        return results

    async def monitor_darkweb(self, query: str) -> list[DarkWebResult]:
        all_results = []
        paste_results = await self.scan_paste_sites(query)
        all_results.extend(paste_results)

        if "@" in query:
            breach_results = await self.scan_breach_databases(query)
            all_results.extend(breach_results)

        all_results.sort(key=lambda x: x.risk_score, reverse=True)
        return all_results

    def _calculate_risk(self, content: str) -> float:
        score = 0.0
        content_lower = content.lower()
        for keyword in self.RISK_KEYWORDS:
            if keyword in content_lower:
                score += 2.0
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        emails = re.findall(email_pattern, content)
        score += len(emails) * 1.5
        ip_pattern = r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
        ips = re.findall(ip_pattern, content)
        score += len(ips) * 1.0
        return min(score, 10.0)

    def _find_keywords(self, content: str) -> list[str]:
        found = []
        content_lower = content.lower()
        for keyword in self.RISK_KEYWORDS + self._monitored_keywords:
            if keyword in content_lower:
                found.append(keyword)
        return found

    async def continuous_monitor(self, interval_seconds: int = 3600) -> None:
        while True:
            for target in self._monitored_targets:
                results = await self.monitor_darkweb(target)
                high_risk = [r for r in results if r.risk_score >= 7.0]
                if high_risk:
                    logger.warning("darkweb_high_risk_detected", target=target, count=len(high_risk))
            await asyncio.sleep(interval_seconds)

dark_web = DarkWebModule()
