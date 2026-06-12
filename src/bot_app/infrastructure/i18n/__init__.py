"""Internationalisation setup (aiogram-i18n + Fluent).

Phase 0 provides the wiring; actual translation files live in ``locales/``.
"""

from __future__ import annotations

from pathlib import Path

from aiogram_i18n import I18nContext, LazyProxy

from ...core.config import settings

__all__ = ["setup_i18n", "LazyProxy"]

_LOCALES_DIR = Path(__file__).resolve().parents[3] / "locales"


def setup_i18n() -> I18nContext:  # type: ignore[misc]
    """Create and return an ``I18nContext`` (stub for Phase 0).

    At Phase 0 we do not wire the i18n middleware yet — we only expose
    ``LazyProxy`` so that handlers can already use ``_("text")`` without
    breaking.  Full middleware wiring comes in Phase 2.
    """
    # Minimal stub: just set the default locale
    return I18nContext(locale=settings.LANGUAGE)  # type: ignore[call-arg]
