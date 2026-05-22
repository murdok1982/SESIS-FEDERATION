"""
NewsAPI.org provider (free tier).

Disabled when ``settings.NEWSAPI_API_KEY`` is empty so deployments
that don't want any third-party API key configured can still use
GDELT + RSS. The API key is passed via the ``X-Api-Key`` header so it
never appears in URLs / logs.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import settings

from .base import (
    OSINTProvider,
    OSINTSignal,
    assert_public_url,
    canonical_url,
    classify_category,
)
from .exceptions import SSRFBlockedError


logger = logging.getLogger(__name__)


_NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"


# Subset of ISO-3166-1 alpha-3 → country names used to make the
# NewsAPI query slightly more discriminating. Falls back to the raw
# code if we don't have a mapping.
_ISO3_TO_NAME = {
    "USA": "United States",
    "RUS": "Russia",
    "CHN": "China",
    "FRA": "France",
    "DEU": "Germany",
    "GBR": "United Kingdom",
    "ESP": "Spain",
    "MEX": "Mexico",
    "BRA": "Brazil",
    "IND": "India",
    "JPN": "Japan",
    "ITA": "Italy",
    "UKR": "Ukraine",
    "TUR": "Turkey",
    "ISR": "Israel",
    "IRN": "Iran",
    "SAU": "Saudi Arabia",
}


def _parse_published(raw: Any) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        s = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)


class NewsAPIProvider(OSINTProvider):
    """NewsAPI.org `/v2/everything` query."""

    name = "newsapi"
    default_reliability = "C"

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.NEWSAPI_API_KEY
        self._endpoint = endpoint or _NEWSAPI_ENDPOINT
        self._client = http_client

    async def execute(
        self,
        country_iso: str,
        days_back: int = 7,
        limit: int = 25,
    ) -> list[OSINTSignal]:
        if not self._api_key:
            # No key configured — provider is intentionally disabled.
            return []

        try:
            assert_public_url(self._endpoint)
        except SSRFBlockedError as exc:
            logger.warning("NewsAPI endpoint blocked by SSRF guard: %s", exc)
            return []

        country = country_iso.upper().strip()
        country_name = _ISO3_TO_NAME.get(country, country) if country else ""
        query = f'"{country_name}"' if country_name else "world"

        from_dt = (datetime.now(timezone.utc) - timedelta(days=days_back)).date()
        params = {
            "q": query,
            "from": from_dt.isoformat(),
            "sortBy": "publishedAt",
            "pageSize": str(min(limit, settings.OSINT_MAX_PER_SOURCE, 100)),
            "language": "en",
        }
        headers = {"X-Api-Key": self._api_key}

        body: dict[str, Any] | None = None
        last_exc: Exception | None = None

        async with self._client_ctx() as client:
            for attempt in range(3):
                try:
                    resp = await client.get(
                        self._endpoint, params=params, headers=headers
                    )
                    resp.raise_for_status()
                    body = resp.json()
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < 2:
                        await asyncio.sleep(1.0 * (attempt + 1))

        if body is None:
            logger.info(
                "NewsAPI fetch failed after retries: %s",
                last_exc.__class__.__name__ if last_exc else "?",
            )
            return []

        articles = body.get("articles") if isinstance(body, dict) else None
        if not isinstance(articles, list):
            return []

        signals: list[OSINTSignal] = []
        for art in articles[: settings.OSINT_MAX_PER_SOURCE]:
            if not isinstance(art, dict):
                continue
            url = str(art.get("url", "") or "")
            title = str(art.get("title", "") or "")
            if not url or not title:
                continue
            try:
                assert_public_url(url)
            except SSRFBlockedError:
                continue
            url = canonical_url(url)

            source_name = "NewsAPI"
            src = art.get("source")
            if isinstance(src, dict):
                source_name = f"NewsAPI:{src.get('name', 'unknown')}"
            description = str(art.get("description", "") or "")
            published = _parse_published(art.get("publishedAt"))
            category = classify_category(f"{title} {description}")

            signals.append(
                OSINTSignal(
                    country=country or "GLOBAL",
                    category=category,
                    title=title[:500],
                    url=url,
                    summary=description[:1000],
                    source_name=source_name,
                    published_at=published,
                    language="en",
                    admiralty_reliability="C",
                    admiralty_credibility=3,
                    confidence_score=0.5,
                    raw_metadata={"newsapi_source": source_name},
                )
            )

        return signals

    def _client_ctx(self):  # noqa: ANN202
        if self._client is not None:
            injected = self._client

            class _Passthrough:
                async def __aenter__(self_inner) -> httpx.AsyncClient:  # noqa: N805
                    return injected

                async def __aexit__(self_inner, exc_type, exc, tb) -> None:  # noqa: N805
                    return None

            return _Passthrough()
        return httpx.AsyncClient(
            timeout=settings.OSINT_HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "GlobalIntelligenceOSINT/1.0 (+state-grade)"},
        )


__all__ = ["NewsAPIProvider"]
