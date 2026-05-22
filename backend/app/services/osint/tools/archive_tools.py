from __future__ import annotations

import time

import httpx

from app.services.osint.tools.base import ToolBase, ToolResult

class ArchiveLookupTool(ToolBase):
    name = "archive_lookup"
    description = "Search Wayback Machine for historical URL captures"
    rate_limit_per_minute = 20

    CDX_URL = "https://web.archive.org/cdx/search/cdx"

    async def execute(self, url: str, limit: int = 20) -> ToolResult:
        await self._rate_limit_check()
        t0 = time.monotonic()
        params = {
            "url": url,
            "output": "json",
            "limit": str(limit),
            "fl": "timestamp,original,statuscode,mimetype,digest",
            "collapse": "digest",
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(self.CDX_URL, params=params)
                resp.raise_for_status()
                rows = resp.json()

            if not rows or len(rows) < 2:
                return ToolResult(
                    success=True,
                    data={"url": url, "snapshots": [], "count": 0},
                    source=self.CDX_URL,
                    method="archive_lookup",
                    duration_ms=(time.monotonic() - t0) * 1000,
                )

            headers = rows[0]
            snapshots = []
            for row in rows[1:]:
                snap = dict(zip(headers, row))
                ts = snap.get("timestamp", "")
                snap["wayback_url"] = f"https://web.archive.org/web/{ts}/{url}" if ts else ""
                snapshots.append(snap)

            return ToolResult(
                success=True,
                data={
                    "url": url,
                    "snapshots": snapshots,
                    "count": len(snapshots),
                    "earliest": snapshots[0].get("timestamp") if snapshots else None,
                    "latest": snapshots[-1].get("timestamp") if snapshots else None,
                },
                source=self.CDX_URL,
                method="archive_lookup",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            return ToolResult(success=False, data=None, source=self.CDX_URL, method="archive_lookup", error=str(exc))
