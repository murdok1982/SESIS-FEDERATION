from __future__ import annotations

import time

import httpx

from app.services.osint.tools.base import ToolBase, ToolResult

class CertSearchTool(ToolBase):
    name = "cert_search"
    description = "Search certificate transparency logs via crt.sh"
    rate_limit_per_minute = 30

    async def execute(self, domain: str, include_subdomains: bool = True) -> ToolResult:
        await self._rate_limit_check()
        t0 = time.monotonic()
        query = f"%.{domain}" if include_subdomains else domain
        url = f"https://crt.sh/?q={query}&output=json"

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, headers={"Accept": "application/json"})
                resp.raise_for_status()
                raw = resp.json()

            seen: set[str] = set()
            certs = []
            subdomains: set[str] = set()

            for entry in raw[:200]:
                name = entry.get("common_name", "") or entry.get("name_value", "")
                if not name or name in seen:
                    continue
                seen.add(name)

                san_names = entry.get("name_value", "").split("\n")
                for san in san_names:
                    san = san.strip().lstrip("*.")
                    if san and san.endswith(domain) and san != domain:
                        subdomains.add(san)

                certs.append({
                    "common_name": name,
                    "issuer": entry.get("issuer_name", ""),
                    "not_before": entry.get("not_before", ""),
                    "not_after": entry.get("not_after", ""),
                    "serial": entry.get("serial_number", ""),
                })

            return ToolResult(
                success=True,
                data={
                    "domain": domain,
                    "certificates": certs[:50],
                    "subdomains": sorted(subdomains),
                    "cert_count": len(certs),
                },
                source=url,
                method="cert_search",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            return ToolResult(success=False, data=None, source=url, method="cert_search", error=str(exc))
