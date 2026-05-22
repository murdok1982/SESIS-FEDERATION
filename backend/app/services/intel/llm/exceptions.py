"""Exceptions raised by the LLM router and its providers."""

from __future__ import annotations


class LLMError(Exception):
    """Base error for all LLM-related failures."""


class ClassificationViolationError(LLMError):
    """Raised when a provider would be asked to handle data above its allowed level.

    This is a *hard* security boundary. The router raises this error
    rather than silently downgrading a request — callers must handle
    or surface it explicitly.
    """


class ProviderUnavailable(LLMError):
    """A provider could not be reached (network, auth, model not loaded, ...)."""


class AllProvidersFailed(LLMError):
    """No provider in the routing chain was able to satisfy the task."""


__all__ = [
    "LLMError",
    "ClassificationViolationError",
    "ProviderUnavailable",
    "AllProvidersFailed",
]
