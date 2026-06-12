"""Payment provider registry — lazy-initialised singleton registry.

Provides a single ``get_provider(name)`` entry point that the rest of
the codebase can call without knowing the concrete provider class.
New providers are registered by calling ``register_provider(name, factory)``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Provider protocol (re-exported from __init__) ─────────────

_PROVIDER_REGISTRY: dict[str, type] = {}
_PROVIDER_INSTANCES: dict[str, object] = {}


def register_provider(name: str, provider_cls: type) -> None:
    """Register a payment provider class under *name*.

    Must be called at import-time (i.e. in ``__init__.py``).
    """
    _PROVIDER_REGISTRY[name] = provider_cls
    logger.debug("payment provider registered: %s → %s", name, provider_cls.__name__)


def get_provider(name: str) -> object | None:
    """Return a cached provider instance for *name*, or ``None`` if unknown.

    The instance is created lazily on first access.
    """
    if name not in _PROVIDER_REGISTRY:
        return None

    if name not in _PROVIDER_INSTANCES:
        cls = _PROVIDER_REGISTRY[name]
        _PROVIDER_INSTANCES[name] = cls()
        logger.debug("payment provider instantiated: %s", name)

    return _PROVIDER_INSTANCES[name]


def list_providers() -> list[str]:
    """Return a sorted list of all registered provider names."""
    return sorted(_PROVIDER_REGISTRY.keys())


def reset() -> None:
    """Reset all cached instances AND the provider registry (useful for testing)."""
    _PROVIDER_INSTANCES.clear()
    _PROVIDER_REGISTRY.clear()
