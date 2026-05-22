from __future__ import annotations

import time

import httpx

from app.services.osint.tools.base import ToolBase, ToolResult

class WhoisTool(ToolBase):
    name = "whois_query"
    description = "WHOIS/RDAP lookup for domains and IPs"
    rate_limit_per_minute = 30

    RDAP_DOMAIN = "https://rdap.org/domain/{}"
    RDAP_IP = "https://rdap.org/ip/{}"

    async def execute(self, target: str) -> ToolResult:
        await self._rate_limit_check()
        t0 = time.monotonic()
        is_ip = self._is_ip(target)
        url = (self.RDAP_IP if is_ip else self.RDAP_DOMAIN).format(target)

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                data = resp.json()

            parsed = self._parse_rdap(data, is_ip)
            return ToolResult(
                success=True,
                data=parsed,
                source=url,
                method="rdap",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception:
            # Fallback to python-whois for domains
            if not is_ip:
                try:
                    import whois  # noqa: PLC0415
                    w = whois.whois(target)
                    return ToolResult(
                        success=True,
                        data={"raw": str(w), "domain": target},
                        source=f"whois:{target}",
                        method="python-whois",
                        duration_ms=(time.monotonic() - t0) * 1000,
                    )
                except Exception as exc2:
                    return ToolResult(success=False, data=None, source=url, method="whois", error=str(exc2))
            return ToolResult(success=False, data=None, source=url, method="rdap", error="RDAP lookup failed")

    def _is_ip(self, target: str) -> bool:
        import re  # noqa: PLC0415
        return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", target) or ":" in target)

    def _parse_rdap(self, data: dict, is_ip: bool) -> dict:
        result: dict = {}
        if is_ip:
            result["type"] = "ip"
            result["handle"] = data.get("handle", "")
            result["start_address"] = data.get("startAddress", "")
            result["end_address"] = data.get("endAddress", "")
            result["name"] = data.get("name", "")
            result["country"] = data.get("country", "")
        else:
            result["type"] = "domain"
            result["handle"] = data.get("handle", "")
            result["ldhName"] = data.get("ldhName", "")
            result["status"] = data.get("status", [])
            result["registrar"] = ""
            result["registrant"] = ""
            result["created"] = ""
            result["expires"] = ""
            result["name_servers"] = [ns.get("ldhName", "") for ns in data.get("nameservers", [])]
            for event in data.get("events", []):
                action = event.get("eventAction", "")
                if action == "registration":
                    result["created"] = event.get("eventDate", "")
                elif action == "expiration":
                    result["expires"] = event.get("eventDate", "")
            for entity in data.get("entities", []):
                roles = entity.get("roles", [])
                vcard = entity.get("vcardArray", [])
                name = ""
                if vcard and len(vcard) > 1:
                    for entry in vcard[1]:
                        if entry[0] == "fn":
                            name = entry[3]
                            break
                if "registrar" in roles:
                    result["registrar"] = name
                if "registrant" in roles:
                    result["registrant"] = name
        return result
