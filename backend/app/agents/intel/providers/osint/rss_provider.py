"""
RSS / Atom OSINT provider.

Reads the curated feed list from ``sources.json`` (sibling file).
Each feed is fetched once per :meth:`execute` call. Per-feed
failures are isolated — one broken source never sinks the scan.

How to add a source
-------------------
Append an object to ``sources.json``::

    {"name": "Example Wire", "url": "https://example.com/feed", "reliability": "B"}

Pick ``reliability`` from the Admiralty alphabet (``A`` highest,
``F`` lowest). The URL MUST point at a public RSS / Atom feed. The
SSRF guard in :mod:`.base` rejects anything that resolves to a
private address at runtime.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

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


_SOURCES_PATH = Path(__file__).with_name("sources.json")


# RSS 1.0 / 2.0 / Atom share enough structure that a manual walker
# keeps us off feedparser. We accept both ``<item>`` (RSS) and
# ``<entry>`` (Atom).
_RFC822_FORMATS = (
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%a, %d %b %Y %H:%M:%S",
)
_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _parse_pub_date(raw: str | None) -> datetime:
    """Best-effort datetime parser. Falls back to ``utcnow``.

    We do not raise on bad dates — losing a few items because a feed
    has a malformed pubDate is worse than tolerating it.
    """
    if not raw:
        return datetime.now(timezone.utc)
    raw = raw.strip()
    # Try RFC 822 variants first.
    for fmt in _RFC822_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    # ISO 8601 fallback.
    if _ISO_RE.match(raw):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _text(elem: ET.Element | None) -> str:
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def _strip_namespace(tag: str) -> str:
    """``{http://www.w3.org/2005/Atom}entry`` → ``entry``."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _load_sources() -> list[dict[str, str]]:
    try:
        return json.loads(_SOURCES_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("RSS sources.json could not be loaded: %s", exc)
        return []


class RSSProvider(OSINTProvider):
    """Curated RSS feed aggregator."""

    name = "rss"

    def __init__(
        self,
        sources: list[dict[str, str]] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._sources = sources if sources is not None else _load_sources()
        self._client = http_client  # injected for tests

    async def execute(
        self,
        country_iso: str,
        days_back: int = 7,
        limit: int = 25,
    ) -> list[OSINTSignal]:
        if not self._sources:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        # Soft cap on combined output. Each source contributes at
        # most ``min(limit, OSINT_MAX_PER_SOURCE)`` entries.
        per_source = min(limit, settings.OSINT_MAX_PER_SOURCE)

        results: list[OSINTSignal] = []

        async with self._client_ctx() as client:
            tasks = [
                self._fetch_one(client, src, country_iso, cutoff, per_source)
                for src in self._sources
            ]
            gathered = await asyncio.gather(*tasks, return_exceptions=True)

        for src, batch in zip(self._sources, gathered):
            if isinstance(batch, Exception):
                logger.warning(
                    "RSS provider %s failed: %s",
                    src.get("name", "?"),
                    batch.__class__.__name__,
                )
                continue
            results.extend(batch)

        # Trim global cap to ``limit`` so a 14-source scan does not
        # explode the per-country signal volume.
        return results[:limit]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _client_ctx(self):  # noqa: ANN202
        """Return a context-manager-friendly httpx client.

        If a client was injected (tests), wrap it in a passthrough
        async context that doesn't close it.
        """
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

    async def _fetch_one(
        self,
        client: httpx.AsyncClient,
        source: dict[str, str],
        country_iso: str,
        cutoff: datetime,
        per_source: int,
    ) -> list[OSINTSignal]:
        url = source.get("url", "")
        name = source.get("name", url)
        reliability = source.get("reliability", "C")

        # SSRF guard before any network call.
        try:
            assert_public_url(url)
        except SSRFBlockedError as exc:
            logger.warning("RSS SSRF blocked for %s: %s", name, exc)
            return []

        # Retry twice with light backoff.
        last_exc: Exception | None = None
        body: bytes | None = None
        for attempt in range(3):
            try:
                response = await client.get(url)
                response.raise_for_status()
                body = response.content
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
        if body is None:
            logger.info(
                "RSS fetch failed for %s after retries: %s",
                name,
                last_exc.__class__.__name__ if last_exc else "?",
            )
            return []

        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            logger.info("RSS parse error for %s: %s", name, exc)
            return []

        signals: list[OSINTSignal] = []
        country_token = country_iso.upper()

        for item in self._iter_items(root):
            title = _text(item.get("title"))
            link = _text(item.get("link"))
            description = _text(item.get("description"))
            pub_raw = _text(item.get("pubDate"))

            if not title or not link:
                continue
            try:
                assert_public_url(link)
            except SSRFBlockedError:
                continue
            link = canonical_url(link)

            published = _parse_pub_date(pub_raw)
            if published < cutoff:
                continue

            # Country filter: keep items that mention the ISO code or
            # the bare token; aggressive filtering happens downstream.
            combined = f"{title} {description}".upper()
            if country_token and country_token not in combined and len(country_token) == 3:
                # Don't drop completely — feeds are world-wide; downstream
                # synthesis can still use them. We just record the
                # country we were asked about in the signal.
                pass

            category = classify_category(f"{title} {description}")
            signals.append(
                OSINTSignal(
                    country=country_token or "GLOBAL",
                    category=category,
                    title=title[:500],
                    url=link,
                    summary=description[:1000],
                    source_name=name,
                    published_at=published,
                    language="auto",
                    admiralty_reliability=reliability,
                    admiralty_credibility=3,
                    confidence_score=0.5,
                    raw_metadata={"feed": name},
                )
            )
            if len(signals) >= per_source:
                break

        return signals

    @staticmethod
    def _iter_items(root: ET.Element):
        """Yield dicts of ``{tag_name: subelement}`` for every entry."""
        # RSS: <rss><channel><item/></channel></rss>
        # Atom: <feed><entry/></feed>
        for elem in root.iter():
            tag = _strip_namespace(elem.tag)
            if tag in {"item", "entry"}:
                d: dict[str, Any] = {}
                for child in list(elem):
                    child_tag = _strip_namespace(child.tag)
                    # Atom <link href="..."/> — surface as text.
                    if (
                        child_tag == "link"
                        and not (child.text or "").strip()
                        and "href" in child.attrib
                    ):
                        clone = ET.Element("link")
                        clone.text = child.attrib["href"]
                        d.setdefault("link", clone)
                        continue
                    # Atom <published> ≈ RSS pubDate.
                    if child_tag in ("published", "updated") and "pubDate" not in d:
                        d.setdefault("pubDate", child)
                        continue
                    # Atom <summary> / <content> ≈ RSS description.
                    if (
                        child_tag in ("summary", "content")
                        and "description" not in d
                    ):
                        d.setdefault("description", child)
                        continue
                    d.setdefault(child_tag, child)
                yield d


__all__ = ["RSSProvider"]
