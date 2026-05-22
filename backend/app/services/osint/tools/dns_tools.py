from __future__ import annotations

import time
from typing import Any

import dns.asyncresolver
import dns.rdatatype

from app.services.osint.tools.base import ToolBase, ToolResult

class DnsLookupTool(ToolBase):
    name = "dns_lookup"
    description = "Passive DNS resolution for domains and IPs"
    rate_limit_per_minute = 120

    async def execute(self, domain: str, record_types: list[str] | None = None) -> ToolResult:
        await self._rate_limit_check()
        if not record_types:
            record_types = ["A", "AAAA", "MX", "TXT", "NS", "SOA"]

        t0 = time.monotonic()
        results: dict[str, Any] = {"domain": domain, "records": {}}
        resolver = dns.asyncresolver.Resolver()

        for rtype in record_types:
            try:
                answer = await resolver.resolve(domain, rtype)
                records = []
                for rdata in answer:
                    records.append(str(rdata))
                results["records"][rtype] = records
            except dns.resolver.NXDOMAIN:
                results["nxdomain"] = True
                break
            except dns.resolver.NoAnswer:
                results["records"][rtype] = []
            except dns.exception.Timeout:
                results["records"][rtype] = ["TIMEOUT"]
            except Exception as exc:
                results["records"][rtype] = [f"ERROR: {exc}"]

        duration_ms = (time.monotonic() - t0) * 1000
        return ToolResult(
            success=True,
            data=results,
            source=f"dns:{domain}",
            method="dns_lookup",
            duration_ms=duration_ms,
        )
