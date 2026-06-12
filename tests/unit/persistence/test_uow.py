"""Tests for the Unit of Work."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot_app.infrastructure.persistence.models import Base, Category, Product, User
from bot_app.infrastructure.persistence.uow import UnitOfWork


# ── Helpers ─────────────────────────────────────────────────────


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[valid-type]
    return async_sessionmaker(engine, expire_on_commit=False)


# ── UnitOfWork ─────────────────────────────────────────────────


class TestUnitOfWork:
    @pytest.mark.asyncio
    async def test_uow_creates_user(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            user = await uow.users.get_or_create(42)
            assert user.id == 42

    @pytest.mark.asyncio
    async def test_uow_commit_persists(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            await uow.users.get_or_create(42)
        # After exiting the context, the user should be committed
        async with UnitOfWork(session_factory) as uow:
            user = await uow.users.get(42)
            assert user is not None
            assert user.id == 42

    @pytest.mark.asyncio
    async def test_uow_rollback_on_exception(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        try:
            async with UnitOfWork(session_factory) as uow:
                await uow.users.get_or_create(99)
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        async with UnitOfWork(session_factory) as uow:
            user = await uow.users.get(99)
            assert user is None

    @pytest.mark.asyncio
    async def test_uow_exposes_all_repos(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            assert uow.users is not None
            assert uow.categories is not None
            assert uow.products is not None
            assert uow.cart_items is not None
            assert uow.orders is not None
            assert uow.order_items is not None
            assert uow.payments is not None

    @pytest.mark.asyncio
    async def test_uow_session_property(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            assert uow.session is not None
            assert isinstance(uow.session, AsyncSession)

    @pytest.mark.asyncio
    async def test_uow_session_property_outside_context(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        uow = UnitOfWork(session_factory)
        with pytest.raises(RuntimeError, match="not active"):
            _ = uow.session

    @pytest.mark.asyncio
    async def test_uow_repo_property_outside_context(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        uow = UnitOfWork(session_factory)
        with pytest.raises(RuntimeError, match="not active"):
            _ = uow.users

    @pytest.mark.asyncio
    async def test_uow_full_flow_category_product_cart(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        """End-to-end: create category, product, user, add to cart — all via UoW."""
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="Electronics", slug="electronics")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id,
                name="Headphones",
                price_smallest_unit=150000,
                stock=10,
            )
            await uow.session.flush()
            user = await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(
                user_id=user.id,
                product_id=prod.id,
                quantity=2,
            )

        # Verify everything was committed
        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            assert len(items) == 1
            assert items[0].quantity == 2
            total_qty = await uow.cart_items.count_items(42)
            assert total_qty == 2
