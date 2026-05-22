"""
LLM router package.

Public API:
    * ``llm_router``: a process-wide :class:`LLMRouter` instance.
    * ``LLMTask``: structured task descriptor that carries classification.
    * ``LLMResult``: structured response.

The router enforces sovereignty rules — see
``app.services.llm.router.LLMRouter`` for details.
"""

from app.services.intel.llm.base import LLMProvider, LLMTask, LLMResult
from app.services.intel.llm.exceptions import (
    ClassificationViolationError,
    ProviderUnavailable,
    AllProvidersFailed,
)
from app.services.intel.llm.router import LLMRouter, llm_router

__all__ = [
    "LLMProvider",
    "LLMTask",
    "LLMResult",
    "LLMRouter",
    "llm_router",
    "ClassificationViolationError",
    "ProviderUnavailable",
    "AllProvidersFailed",
]
