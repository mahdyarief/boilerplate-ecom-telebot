"""Tests for StockWar Protection — atomic reserve/release/confirm operations.

These tests verify that:

1. ``reserve_stock`` atomically decrements stock only when sufficient
2. ``release_stock`` increments stock back
3. ``confirm_stock`` is a no-op (already decremented)
4. Concurrent reservations cannot exceed available stock
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot_app.infrastructure.persistence.models import Base, Category, Product, User
from bot_app.infrastructure.persistence.uow import UnitOfWork


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[valid-type]
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_product(
    session_factory: async_sessionmaker[AsyncSession],  # type: ignore[valid-type]
    stock: int = 10,
) -> Product:
    """Create a product with given stock, return its id."""
    async with UnitOfWork(session_factory) as uow:
        cat = await uow.categories.create(name="Test", slug="test-stock-war")
        await uow.session.flush()
        prod = await uow.products.create(
            category_id=cat.id,
            name="Widget",
            price_smallest_unit=50000,
            stock=stock,
        )
    return prod


# ── reserve_stock ────────────────────────────────────────────


class TestReserveStock:
    @pytest.mark.asyncio
    async def test_reserve_succeeds_when_stock_sufficient(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        prod = await _seed_product(session_factory, stock=10)

        async with UnitOfWork(session_factory) as uow:
            result = await uow.products.reserve_stock(prod.id, 5)

        assert result is True

        # Verify stock was decremented
        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(prod.id)
        assert product is not None
        assert product.stock == 5

    @pytest.mark.asyncio
    async def test_reserve_fails_when_stock_insufficient(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        prod = await _seed_product(session_factory, stock=3)

        async with UnitOfWork(session_factory) as uow:
            result = await uow.products.reserve_stock(prod.id, 5)

        assert result is False

        # Verify stock was NOT decremented
        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(prod.id)
        assert product is not None
        assert product.stock == 3

    @pytest.mark.asyncio
    async def test_reserve_exact_stock(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        prod = await _seed_product(session_factory, stock=5)

        async with UnitOfWork(session_factory) as uow:
            result = await uow.products.reserve_stock(prod.id, 5)

        assert result is True

        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(prod.id)
        assert product is not None
        assert product.stock == 0

    @pytest.mark.asyncio
    async def test_reserve_zero_quantity_always_succeeds(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        prod = await _seed_product(session_factory, stock=0)

        async with UnitOfWork(session_factory) as uow:
            result = await uow.products.reserve_stock(prod.id, 0)

        assert result is True

    @pytest.mark.asyncio
    async def test_reserve_from_zero_stock_fails(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        prod = await _seed_product(session_factory, stock=0)

        async with UnitOfWork(session_factory) as uow:
            result = await uow.products.reserve_stock(prod.id, 1)

        assert result is False


# ── release_stock ───────────────────────────────────────────


class TestReleaseStock:
    @pytest.mark.asyncio
    async def test_release_increments_stock(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        prod = await _seed_product(session_factory, stock=10)

        async with UnitOfWork(session_factory) as uow:
            await uow.products.reserve_stock(prod.id, 5)

        async with UnitOfWork(session_factory) as uow:
            await uow.products.release_stock(prod.id, 3)

        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(prod.id)
        assert product is not None
        assert product.stock == 8  # 10 - 5 + 3

    @pytest.mark.asyncio
    async def test_release_restores_all_stock(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        prod = await _seed_product(session_factory, stock=10)

        async with UnitOfWork(session_factory) as uow:
            await uow.products.reserve_stock(prod.id, 10)

        async with UnitOfWork(session_factory) as uow:
            await uow.products.release_stock(prod.id, 10)

        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(prod.id)
        assert product is not None
        assert product.stock == 10


# ── confirm_stock ──────────────────────────────────────────


class TestConfirmStock:
    @pytest.mark.asyncio
    async def test_confirm_is_noop(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """confirm_stock should not change stock (already decremented at reserve time)."""
        prod = await _seed_product(session_factory, stock=10)

        async with UnitOfWork(session_factory) as uow:
            await uow.products.reserve_stock(prod.id, 5)

        async with UnitOfWork(session_factory) as uow:
            await uow.products.confirm_stock(prod.id, 5)

        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(prod.id)
        assert product is not None
        assert product.stock == 5  # unchanged from after reserve


# ── Stock War — concurrent reservations ────────────────────


class TestStockWarConcurrent:
    @pytest.mark.asyncio
    async def test_concurrent_reservations_cannot_exceed_stock(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Two users reserving 8 items each from a stock of 10.

        Only one should succeed; the other should fail.
        """
        prod = await _seed_product(session_factory, stock=10)

        results: list[bool] = []

        async def _reserve(qty: int) -> None:
            async with UnitOfWork(session_factory) as uow:
                ok = await uow.products.reserve_stock(prod.id, qty)
                results.append(ok)

        # Run both reservations concurrently
        await asyncio.gather(_reserve(8), _reserve(8))

        # Exactly one should have succeeded
        assert results.count(True) == 1
        assert results.count(False) == 1

        # Verify stock is 2 (10 - 8)
        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(prod.id)
        assert product is not None
        assert product.stock == 2

    @pytest.mark.asyncio
    async def test_sequential_reservations_deplete_stock(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Sequential reservations should correctly deplete stock."""
        prod = await _seed_product(session_factory, stock=10)

        # Reserve 6
        async with UnitOfWork(session_factory) as uow:
            assert await uow.products.reserve_stock(prod.id, 6) is True

        # Reserve 4 (exactly the rest)
        async with UnitOfWork(session_factory) as uow:
            assert await uow.products.reserve_stock(prod.id, 4) is True

        # Try to reserve 1 more — should fail
        async with UnitOfWork(session_factory) as uow:
            assert await uow.products.reserve_stock(prod.id, 1) is False

    @pytest.mark.asyncio
    async def test_reserve_release_reserve_cycle(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """After releasing reserved stock, it becomes available again."""
        prod = await _seed_product(session_factory, stock=5)

        # Reserve 5
        async with UnitOfWork(session_factory) as uow:
            assert await uow.products.reserve_stock(prod.id, 5) is True

        # Try to reserve 1 — fail
        async with UnitOfWork(session_factory) as uow:
            assert await uow.products.reserve_stock(prod.id, 1) is False

        # Release 3
        async with UnitOfWork(session_factory) as uow:
            await uow.products.release_stock(prod.id, 3)

        # Now reserve 2 — should succeed (stock is 3 after release)
        async with UnitOfWork(session_factory) as uow:
            assert await uow.products.reserve_stock(prod.id, 2) is True

        # Reserve 2 more — should fail (only 1 left)
        async with UnitOfWork(session_factory) as uow:
            assert await uow.products.reserve_stock(prod.id, 2) is False
