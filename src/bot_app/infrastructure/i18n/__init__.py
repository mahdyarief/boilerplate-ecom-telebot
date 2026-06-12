"""Internationalisation — lightweight dict-based i18n system.

Phase 6 replaces the Phase 0 stub with a working implementation:

- ``translations.py`` — translation dictionaries for ``id`` / ``en``
  and the ``t(key, lang)`` lookup function.
- ``middleware.py`` — ``LanguageMiddleware`` that injects the user's
  language preference into handler data.

Usage in handlers::

    from ...infrastructure.i18n import t

    text = t("cart.empty", data["lang"])

Usage in text formatters::

    from ...infrastructure.i18n import t

    def fmt_empty_cart(lang: str) -> str:
        return t("cart.empty", lang)
"""

from .middleware import LanguageMiddleware
from .translations import available_languages, t

__all__ = ["LanguageMiddleware", "available_languages", "t"]
