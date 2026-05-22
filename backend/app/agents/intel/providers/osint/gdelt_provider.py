"""
GDELT 2.0 document-level API provider.

Uses the public GDELT doc API
(``https://api.gdeltproject.org/api/v2/doc/doc``) which returns JSON
when ``format=json`` is appended. The endpoint is open and does not
require an API key, but it rate-limits per IP. We respect that with
explicit retries + backoff.

GDELT is an automated aggregator of open news; the Admiralty
reliability is set to ``C`` (fairly reliable). Credibility starts at
3 (possibly true) and may be promoted later when the OSINT agent
correlates the same story across multiple providers.
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


# YYYYMMDDHHMMSS for the GDELT date params.
_GDELT_DATE_FMT = "%Y%m%d%H%M%S"


def _parse_seendate(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.strptime(raw, _GDELT_DATE_FMT).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return datetime.now(timezone.utc)


class GDELTProvider(OSINTProvider):
    """GDELT 2.0 document API."""

    name = "gdelt"
    default_reliability = "C"

    def __init__(
        self,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url or settings.GDELT_BASE_URL
        self._client = http_client

    async def execute(
        self,
        country_iso: str,
        days_back: int = 7,
        limit: int = 25,
    ) -> list[OSINTSignal]:
        if not self._base_url:
            return []

        try:
            assert_public_url(self._base_url)
        except SSRFBlockedError as exc:
            logger.warning("GDELT base URL blocked by SSRF guard: %s", exc)
            return []

        # GDELT uses 2-letter FIPS-like or 3-letter country codes; we
        # build both forms to maximize hits.
        country = country_iso.upper().strip()
        query_country = f'sourcecountry:{country[:2]}' if country else ""

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days_back)
        params = {
            "query": query_country or "news",
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(min(limit, settings.OSINT_MAX_PER_SOURCE)),
            "startdatetime": start.strftime(_GDELT_DATE_FMT),
            "enddatetime": now.strftime(_GDELT_DATE_FMT),
            "sort": "DateDesc",
        }

        body: dict[str, Any] | None = None
        last_exc: Exception | None = None

        async with self._client_ctx() as client:
            for attempt in range(3):
                try:
                    resp = await client.get(self._base_url, params=params)
                    resp.raise_for_status()
                    body = resp.json()
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < 2:
                        await asyncio.sleep(1.0 * (attempt + 1))

        if body is None:
            logger.info(
                "GDELT fetch failed after retries: %s",
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

            language = str(art.get("language", "auto") or "auto").lower()
            domain = str(art.get("domain", "") or "")
            seendate = _parse_seendate(art.get("seendate"))
            category = classify_category(title)

            signals.append(
                OSINTSignal(
                    country=country or "GLOBAL",
                    category=category,
                    title=title[:500],
                    url=url,
                    summary="",
                    source_name=f"GDELT:{domain}" if domain else "GDELT",
                    published_at=seendate,
                    language=language,
                    admiralty_reliability="C",
                    admiralty_credibility=3,
                    confidence_score=0.45,
                    raw_metadata={
                        "domain": domain,
                        "sourcecountry": art.get("sourcecountry"),
                    },
                )
            )

        return signals

    # ------------------------------------------------------------------
    # httpx client management — identical pattern to RSSProvider so we
    # share behaviour without forcing inheritance.
    # ------------------------------------------------------------------
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


__all__ = ["GDELTProvider"]
