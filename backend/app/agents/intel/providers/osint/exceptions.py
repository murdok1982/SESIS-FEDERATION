"""Exceptions specific to OSINT provider plugins."""


class OSINTProviderError(Exception):
    """Base class — all provider-level failures."""


class SSRFBlockedError(OSINTProviderError):
    """A URL resolved to a private / loopback / link-local IP."""


class ProviderHTTPError(OSINTProviderError):
    """Underlying HTTP transport failed after all retries."""


class ProviderParseError(OSINTProviderError):
    """Provider returned data we cannot decode into OSINTSignal."""


__all__ = [
    "OSINTProviderError",
    "SSRFBlockedError",
    "ProviderHTTPError",
    "ProviderParseError",
]
