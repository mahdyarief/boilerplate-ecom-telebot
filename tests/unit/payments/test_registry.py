"""Tests for the payment provider registry."""

from __future__ import annotations

import pytest

from bot_app.infrastructure.payments.registry import (
    get_provider,
    list_providers,
    register_provider,
    reset,
)


class DummyProvider:
    """A dummy payment provider for testing the registry."""

    pass


class AnotherProvider:
    """Another dummy provider."""

    pass


class TestPaymentRegistry:
    def setup_method(self) -> None:
        """Reset the registry before each test."""
        reset()

    def test_register_and_get_provider(self) -> None:
        register_provider("dummy", DummyProvider)
        provider = get_provider("dummy")
        assert provider is not None
        assert isinstance(provider, DummyProvider)

    def test_get_unknown_provider_returns_none(self) -> None:
        assert get_provider("nonexistent") is None

    def test_list_providers_empty(self) -> None:
        assert list_providers() == []

    def test_list_providers_after_register(self) -> None:
        register_provider("alpha", DummyProvider)
        register_provider("beta", AnotherProvider)
        providers = list_providers()
        assert providers == ["alpha", "beta"]  # sorted

    def test_provider_is_cached(self) -> None:
        register_provider("cached", DummyProvider)
        p1 = get_provider("cached")
        p2 = get_provider("cached")
        assert p1 is p2  # same instance

    def test_reset_clears_instances(self) -> None:
        register_provider("temp", DummyProvider)
        p1 = get_provider("temp")
        reset()
        p2 = get_provider("temp")
        assert p1 is not p2  # different instances after reset

    def test_register_overwrites(self) -> None:
        register_provider("overwrite", DummyProvider)
        register_provider("overwrite", AnotherProvider)
        provider = get_provider("overwrite")
        assert isinstance(provider, AnotherProvider)
