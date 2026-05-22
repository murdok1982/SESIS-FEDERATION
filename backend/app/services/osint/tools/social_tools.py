from __future__ import annotations

import time

import httpx

from app.services.osint.tools.base import ToolBase, ToolResult

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AtalayaBot/0.1; Research)",
    "Accept": "application/json, text/html;q=0.9",
}

class SocialProfileFetchTool(ToolBase):
    name = "social_profile_fetch"
    description = "Fetch public social media profiles (PUBLIC data only)"
    rate_limit_per_minute = 10

    PLATFORM_APIS = {
        "github": "https://api.github.com/users/{handle}",
        "reddit": "https://www.reddit.com/user/{handle}/about.json",
    }

    async def execute(self, handle: str, platforms: list[str] | None = None) -> ToolResult:
        await self._rate_limit_check()
        t0 = time.monotonic()
        results: dict = {}
        check_platforms = platforms or ["github", "reddit"]

        for platform in check_platforms:
            api_url = self.PLATFORM_APIS.get(platform)
            if not api_url:
                results[platform] = {"exists": None, "error": "no_api"}
                continue

            url = api_url.format(handle=handle)
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(url, headers=_DEFAULT_HEADERS, follow_redirects=True)

                if resp.status_code == 404:
                    results[platform] = {"exists": False}
                    continue
                if resp.status_code != 200:
                    results[platform] = {"exists": None, "error": f"http_{resp.status_code}"}
                    continue

                data = resp.json()
                if platform == "github":
                    results[platform] = {
                        "exists": True,
                        "display_name": data.get("name"),
                        "bio": data.get("bio"),
                        "follower_count": data.get("followers"),
                        "post_count": data.get("public_repos"),
                        "join_date": data.get("created_at"),
                        "is_verified": False,
                        "profile_url": data.get("html_url"),
                        "blog": data.get("blog"),
                        "company": data.get("company"),
                        "location": data.get("location"),
                    }
                elif platform == "reddit":
                    rdata = data.get("data", {})
                    results[platform] = {
                        "exists": True,
                        "display_name": rdata.get("name"),
                        "bio": rdata.get("subreddit", {}).get("public_description"),
                        "follower_count": rdata.get("total_karma"),
                        "join_date": str(rdata.get("created_utc", "")),
                        "is_verified": rdata.get("verified", False),
                        "profile_url": f"https://reddit.com/user/{handle}",
                    }
            except Exception as exc:
                results[platform] = {"exists": None, "error": str(exc)}

        return ToolResult(
            success=True,
            data={"handle": handle, "profiles": results},
            source="social_profile_fetch",
            method="social_profile_fetch",
            duration_ms=(time.monotonic() - t0) * 1000,
        )
