"""Application routing — re-exports the command registry and dispatcher for
backward compatibility with the custom routing layer.

NOTE: The primary routing in Phase 0+ uses aiogram's built-in ``Dispatcher``
and ``Router`` system.  The custom ``CommandRegistry`` and ``Dispatcher`` here
support the low-level polling / gateway path when it is needed.
"""

from .command_registry import CommandRegistry
from .dispatcher import Dispatcher

__all__ = ["CommandRegistry", "Dispatcher"]
