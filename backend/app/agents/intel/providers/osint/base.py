"""
Base contracts for OSINT provider plugins.

Every provider implements :class:`OSINTProvider` and returns a list
of :class:`OSINTSignal` records. The signals carry classification
metadata (Admiralty reliability / credibility) so the downstream
correlation step can compute a confidence_score per signal.

Security invariants enforced here:

* :func:`assert_public_url` blocks any URL that resolves to a
  private, loopback, link-local, multicast or reserved IP — without
  this guard a malicious feed could pivot an outbound fetch into the
  application's internal network (SSRF).
* :func:`canonical_url` strips ``utm_*`` and ``fbclid`` query params
  so duplicate signals across feeds dedupe cleanly. Lowercased host,
  no trailing slash.

We never log full article bodies. Provider implementations are
expected to log titles and URLs only — never the body extracted from
a feed.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from .exceptions import SSRFBlockedError


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signal model
# ---------------------------------------------------------------------------


@dataclass
class OSINTSignal:
    """A normalized signal emitted by any OSINT provider.

    The dataclass is intentionally lightweight — providers map their
    own data into it, the OSINT agent aggregates them, and downstream
    LLM synthesis treats them as opaque structured input.
    """

    country: str
    category: str  # economic / security / defense / political / social / other
    title: str
    url: str
    summary: str
    source_name: str
    published_at: datetime
    language: str
    admiralty_reliability: str  # A B C D E F
    admiralty_credibility: int  # 1..6
    confidence_score: float
    raw_metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Category keywords — shared by all providers
# ---------------------------------------------------------------------------


_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "defense": (
        # ES
        "militar",
        "defensa",
        "ejército",
        "ejercito",
        "armamento",
        "armas",
        "tropas",
        "otan",
        # EN
        "military",
        "defense",
        "defence",
        "army",
        "weapons",
        "missile",
        "nato",
        "troop",
    ),
    "security": (
        "terrorismo",
        "atentado",
        "cibera",
        "ciberataque",
        "ciberseguridad",
        "seguridad nacional",
        "terror",
        "terrorism",
        "cyber",
        "cyberattack",
        "ransomware",
        "espionage",
        "espionaje",
    ),
    "political": (
        "elecciones",
        "elección",
        "gobierno",
        "presidente",
        "parlamento",
        "election",
        "government",
        "president",
        "parliament",
        "minister",
        "diplomacy",
        "sanction",
        "sanción",
        "sancion",
    ),
    "economic": (
        "economía",
        "economia",
        "inflación",
        "inflacion",
        "pib",
        "bolsa",
        "economy",
        "inflation",
        "gdp",
        "trade",
        "tariff",
        "central bank",
        "imf",
        "fmi",
    ),
    "social": (
        "protesta",
        "manifestación",
        "manifestacion",
        "huelga",
        "protest",
        "strike",
        "riot",
        "demonstration",
        "unrest",
    ),
}


def classify_category(text: str) -> str:
    """Cheap keyword-based categorizer.

    Picks the category with the highest count of keyword hits.
    Falls back to ``"other"`` when nothing matches. The LLM
    downstream may override this — keyword classification only
    powers the initial filtering / dashboards.
    """
    if not text:
        return "other"
    lowered = text.lower()
    best: tuple[str, int] = ("other", 0)
    for category, words in _CATEGORY_KEYWORDS.items():
        hits = sum(1 for w in words if w in lowered)
        if hits > best[1]:
            best = (category, hits)
    return best[0]


# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------


_BAD_SCHEMES = {"file", "ftp", "gopher", "data", "javascript", "ldap"}


def assert_public_url(url: str) -> None:
    """Raise SSRFBlockedError if ``url`` is anything we will not fetch.

    Rules:
        * Only ``http`` and ``https`` are accepted.
        * Host must be present.
        * If the host is an IP literal it must be globally routable.
        * If the host is a name, every A/AAAA record returned by DNS
          must also be globally routable.

    DNS lookups go through ``socket.getaddrinfo`` synchronously. This
    is acceptable because providers call this helper at most a few
    dozen times per scan and ``httpx`` would do the same lookup
    anyway during the request.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in _BAD_SCHEMES or scheme not in {"http", "https"}:
        raise SSRFBlockedError(f"scheme {scheme!r} not allowed")
    host = parsed.hostname
    if not host:
        raise SSRFBlockedError("URL has no host")

    # IP literal?
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None

    addresses: list[ipaddress._BaseAddress] = []
    if ip is not None:
        addresses.append(ip)
    else:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise SSRFBlockedError(f"DNS lookup failed for {host}: {exc}") from exc
        seen: set[str] = set()
        for info in infos:
            sockaddr = info[4]
            ip_str = sockaddr[0]
            if ip_str in seen:
                continue
            seen.add(ip_str)
            try:
                addresses.append(ipaddress.ip_address(ip_str))
            except ValueError:
                # Skip unknown address family.
                continue

    if not addresses:
        raise SSRFBlockedError(f"no usable addresses for {host}")

    for addr in addresses:
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        ):
            raise SSRFBlockedError(
                f"host {host} resolves to non-public address {addr}"
            )


# ---------------------------------------------------------------------------
# URL canonicalization
# ---------------------------------------------------------------------------


_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "ref_url",
}


def canonical_url(url: str) -> str:
    """Strip tracking params and lowercase the host.

    Idempotent: ``canonical_url(canonical_url(x)) == canonical_url(x)``.
    """
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return url
    if not parsed.scheme or not parsed.netloc:
        return url
    netloc = parsed.netloc.lower()
    # Drop default ports.
    if netloc.endswith(":80") and parsed.scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and parsed.scheme == "https":
        netloc = netloc[:-4]
    path = re.sub(r"/+$", "", parsed.path or "")
    query_pairs = [
        (k, v)
        for (k, v) in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query_pairs.sort()
    query = urlencode(query_pairs, doseq=True)
    return urlunparse(
        (parsed.scheme.lower(), netloc, path, "", query, "")
    )


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------


class OSINTProvider(ABC):
    """Common contract for OSINT plugins.

    Concrete providers MUST set :attr:`name` and implement
    :meth:`execute`. They return an empty list on failure rather than
    raising — the OSINT agent treats individual provider failures as
    soft, not hard.
    """

    name: str = "unknown"
    default_reliability: str = "C"

    @abstractmethod
    async def execute(
        self,
        country_iso: str,
        days_back: int = 7,
        limit: int = 25,
    ) -> list[OSINTSignal]:
        raise NotImplementedError


__all__ = [
    "OSINTSignal",
    "OSINTProvider",
    "assert_public_url",
    "canonical_url",
    "classify_category",
]
