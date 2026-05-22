from __future__ import annotations

import ipaddress
import time
from urllib.parse import urlparse

import httpx

from app.services.osint.tools.base import ToolBase, ToolResult

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.google",
    "169.254.169.254",
}

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AtalayaBot/0.1; OSINT Research)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

def _is_safe_url(url: str) -> bool:
    """SSRF prevention: block private/internal IPs and known internal hostnames."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        if not host:
            return False
        if host.lower() in _BLOCKED_HOSTNAMES:
            return False
        try:
            addr = ipaddress.ip_address(host)
            return not any(addr in net for net in _BLOCKED_NETWORKS)
        except ValueError:
            # Hostname — block if it ends with .local, .internal, or .localhost
            lower = host.lower()
            if lower.endswith((".local", ".internal", ".localhost", ".localdomain")):
                return False
            return True
    except Exception:
        return False

class WebFetchTool(ToolBase):
    name = "web_fetch"
    description = "Fetch and extract text from public web pages"
    rate_limit_per_minute = 30

    def __init__(self, config=None) -> None:
        self.config = config

    async def execute(
        self,
        url: str,
        extract_text: bool = True,
        follow_redirects: bool = True,
        timeout: int = 30,
    ) -> ToolResult:
        if not _is_safe_url(url):
            return ToolResult(success=False, data=None, source=url, method="web_fetch", error="URL blocked (SSRF protection)")

        await self._rate_limit_check()
        t0 = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects) as client:
                resp = await client.get(url, headers=_DEFAULT_HEADERS)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                final_url = str(resp.url)
                raw_html = resp.text

            text = ""
            title = ""
            links: list[str] = []

            if extract_text and "html" in content_type:
                try:
                    import trafilatura  # noqa: PLC0415
                    text = trafilatura.extract(raw_html) or ""
                except Exception:
                    pass

                if not text:
                    from bs4 import BeautifulSoup  # noqa: PLC0415
                    soup = BeautifulSoup(raw_html, "lxml")
                    text = soup.get_text(separator=" ", strip=True)[:10000]
                    title_tag = soup.find("title")
                    title = title_tag.get_text(strip=True) if title_tag else ""
                    links = [a.get("href", "") for a in soup.find_all("a", href=True)][:50]

            return ToolResult(
                success=True,
                data={
                    "url": url,
                    "final_url": final_url,
                    "status_code": resp.status_code,
                    "content_type": content_type,
                    "title": title,
                    "text": text[:8000] if text else "",
                    "links": links,
                },
                source=final_url,
                method="web_fetch",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            return ToolResult(success=False, data=None, source=url, method="web_fetch", error=str(exc))

class WebSearchTool(ToolBase):
    name = "web_search"
    description = "Public web search via DuckDuckGo"
    rate_limit_per_minute = 10

    async def execute(self, query: str, num_results: int = 10) -> ToolResult:
        await self._rate_limit_check()
        t0 = time.monotonic()
        try:
            from duckduckgo_search import DDGS  # noqa: PLC0415
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=num_results))
            return ToolResult(
                success=True,
                data={"query": query, "results": results},
                source="duckduckgo",
                method="web_search",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            return ToolResult(success=False, data=None, source="duckduckgo", method="web_search", error=str(exc))

class IpGeolocationTool(ToolBase):
    name = "ip_geolocation"
    description = "Geolocation of public IP addresses"
    rate_limit_per_minute = 45

    def __init__(self, config=None) -> None:
        self.config = config

    async def execute(self, ip: str) -> ToolResult:
        await self._rate_limit_check()
        t0 = time.monotonic()

        # Validate it's not a private IP
        try:
            addr = ipaddress.ip_address(ip)
            if any(addr in net for net in _BLOCKED_NETWORKS):
                return ToolResult(success=False, data=None, source=ip, method="ip_geolocation", error="Private IP")
        except ValueError:
            return ToolResult(success=False, data=None, source=ip, method="ip_geolocation", error="Invalid IP")

        url = f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,region,regionName,city,lat,lon,timezone,isp,org,as,asname"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            if data.get("status") == "fail":
                return ToolResult(success=False, data=None, source=url, method="ip_geolocation", error=data.get("message", ""))

            return ToolResult(
                success=True,
                data=data,
                source=url,
                method="ip_geolocation",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            return ToolResult(success=False, data=None, source=url, method="ip_geolocation", error=str(exc))
