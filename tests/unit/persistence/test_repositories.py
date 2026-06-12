"""Tests for the repository layer — all run against in-memory SQLite."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot_app.core.constants import OrderStatus, PaymentStatus
from bot_app.infrastructure.persistence.models import (
    Category,
    OrderItem,
    Product,
    User,
)
from bot_app.infrastructure.persistence.repositories import (
    CartItemRepository,
    CategoryRepository,
    OrderItemRepository,
    OrderRepository,
    PaymentRepository,
    ProductRepository,
    UserRepository,
)

# ── Helpers ─────────────────────────────────────────────────────


async def _make_category(session: AsyncSession, **kw) -> Category:
    repo = CategoryRepository(session)
    return await repo.create(**kw)


async def _make_product(session: AsyncSession, **kw) -> Product:
    repo = ProductRepository(session)
    return await repo.create(**kw)


async def _make_user(session: AsyncSession, user_id: int = 42, **kw) -> User:
    repo = UserRepository(session)
    return await repo.get_or_create(user_id, **kw)


# ── UserRepository ──────────────────────────────────────────────


class TestUserRepository:
    @pytest.mark.asyncio
    async def test_get_or_create_creates_new(self, session: AsyncSession) -> None:
        repo = UserRepository(session)
        user = await repo.get_or_create(123, language="en")
        await session.flush()
        assert user.id == 123
        assert user.language == "en"
        assert user.is_admin is False

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing(self, session: AsyncSession) -> None:
        repo = UserRepository(session)
        await repo.get_or_create(123)
        await session.flush()
        user2 = await repo.get_or_create(123, language="en")
        assert user2.language == "id"  # not overwritten

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing(self, session: AsyncSession) -> None:
        repo = UserRepository(session)
        assert await repo.get(999) is None

    @pytest.mark.asyncio
    async def test_set_language(self, session: AsyncSession) -> None:
        repo = UserRepository(session)
        await repo.get_or_create(123, language="id")
        await session.flush()
        await repo.set_language(123, "en")
        await session.flush()
        user = await repo.get(123)
        assert user is not None
        assert user.language == "en"

    @pytest.mark.asyncio
    async def test_toggle_admin(self, session: AsyncSession) -> None:
        repo = UserRepository(session)
        await repo.get_or_create(123)
        await session.flush()
        await repo.toggle_admin(123, is_admin=True)
        await session.flush()
        user = await repo.get(123)
        assert user is not None
        assert user.is_admin is True

    @pytest.mark.asyncio
    async def test_list_admins(self, session: AsyncSession) -> None:
        repo = UserRepository(session)
        await repo.get_or_create(1)
        await repo.get_or_create(2)
        await session.flush()
        await repo.toggle_admin(2, is_admin=True)
        await session.flush()
        admins = await repo.list_admins()
        assert len(admins) == 1
        assert admins[0].id == 2


# ── CategoryRepository ─────────────────────────────────────────


class TestCategoryRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, session: AsyncSession) -> None:
        repo = CategoryRepository(session)
        cat = await repo.create(name="Electronics", slug="electronics")
        await session.flush()
        found = await repo.get(cat.id)
        assert found is not None
        assert found.slug == "electronics"

    @pytest.mark.asyncio
    async def test_get_by_slug(self, session: AsyncSession) -> None:
        repo = CategoryRepository(session)
        await repo.create(name="Fashion", slug="fashion")
        await session.flush()
        found = await repo.get_by_slug("fashion")
        assert found is not None
        assert found.name == "Fashion"

    @pytest.mark.asyncio
    async def test_list_active(self, session: AsyncSession) -> None:
        repo = CategoryRepository(session)
        await repo.create(name="A", slug="a", position=2)
        await repo.create(name="B", slug="b", position=1)
        await session.flush()
        result = await repo.list_active()
        assert len(result) == 2
        # Ordered by position then id
        assert result[0].slug == "b"  # position=1
        assert result[1].slug == "a"  # position=2

    @pytest.mark.asyncio
    async def test_list_active_with_parent(self, session: AsyncSession) -> None:
        repo = CategoryRepository(session)
        parent = await repo.create(name="Electronics", slug="electronics")
        await session.flush()
        await repo.create(
            name="Phones", slug="phones", parent_id=parent.id,
        )
        await session.flush()

        # Root categories (no parent)
        roots = await repo.list_active()
        assert len(roots) == 1
        assert roots[0].slug == "electronics"

        # Children of Electronics
        children = await repo.list_active(parent_id=parent.id)
        assert len(children) == 1
        assert children[0].slug == "phones"

    @pytest.mark.asyncio
    async def test_update(self, session: AsyncSession) -> None:
        repo = CategoryRepository(session)
        cat = await repo.create(name="Old", slug="old")
        await session.flush()
        await repo.update(cat.id, name="New", slug="new")
        await session.flush()
        found = await repo.get(cat.id)
        assert found is not None
        assert found.name == "New"

    @pytest.mark.asyncio
    async def test_toggle_active(self, session: AsyncSession) -> None:
        repo = CategoryRepository(session)
        cat = await repo.create(name="X", slug="x")
        await session.flush()
        await repo.toggle_active(cat.id, is_active=False)
        await session.flush()
        found = await repo.get(cat.id)
        assert found is not None
        assert found.is_active is False


# ── ProductRepository ──────────────────────────────────────────


class TestProductRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, session: AsyncSession) -> None:
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        repo = ProductRepository(session)
        prod = await repo.create(
            category_id=cat.id, name="Widget", price_smallest_unit=50000,
        )
        await session.flush()
        found = await repo.get(prod.id)
        assert found is not None
        assert found.name == "Widget"

    @pytest.mark.asyncio
    async def test_list_by_category(self, session: AsyncSession) -> None:
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        repo = ProductRepository(session)
        await repo.create(category_id=cat.id, name="P1", price_smallest_unit=100)
        await repo.create(category_id=cat.id, name="P2", price_smallest_unit=200)
        await session.flush()
        prods = await repo.list_by_category(cat.id)
        assert len(prods) == 2

    @pytest.mark.asyncio
    async def test_update_stock(self, session: AsyncSession) -> None:
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        repo = ProductRepository(session)
        prod = await repo.create(
            category_id=cat.id, name="P", price_smallest_unit=100, stock=10,
        )
        await session.flush()
        await repo.update_stock(prod.id, delta=-3)
        await session.flush()
        found = await repo.get(prod.id)
        assert found is not None
        assert found.stock == 7

    @pytest.mark.asyncio
    async def test_toggle_active(self, session: AsyncSession) -> None:
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        repo = ProductRepository(session)
        prod = await repo.create(
            category_id=cat.id, name="P", price_smallest_unit=100,
        )
        await session.flush()
        await repo.toggle_active(prod.id, is_active=False)
        await session.flush()
        found = await repo.get(prod.id)
        assert found is not None
        assert found.is_active is False

    @pytest.mark.asyncio
    async def test_list_by_category_active_only(self, session: AsyncSession) -> None:
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        repo = ProductRepository(session)
        p1 = await repo.create(category_id=cat.id, name="Active", price_smallest_unit=100)  # noqa: F841
        p2 = await repo.create(category_id=cat.id, name="Inactive", price_smallest_unit=200)
        await session.flush()
        await repo.toggle_active(p2.id, is_active=False)
        await session.flush()

        active = await repo.list_by_category(cat.id, active_only=True)
        assert len(active) == 1
        assert active[0].name == "Active"


# ── CartItemRepository ──────────────────────────────────────────


class TestCartItemRepository:
    @pytest.mark.asyncio
    async def test_add_item(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        prod = await _make_product(
            session, category_id=cat.id, name="P", price_smallest_unit=100,
        )
        await session.flush()

        repo = CartItemRepository(session)
        item = await repo.add_item(user_id=user.id, product_id=prod.id, quantity=2)
        await session.flush()
        assert item.quantity == 2

    @pytest.mark.asyncio
    async def test_add_item_increments_existing(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        prod = await _make_product(
            session, category_id=cat.id, name="P", price_smallest_unit=100,
        )
        await session.flush()

        repo = CartItemRepository(session)
        await repo.add_item(user_id=user.id, product_id=prod.id, quantity=1)
        await session.flush()
        item = await repo.add_item(user_id=user.id, product_id=prod.id, quantity=3)
        await session.flush()
        assert item.quantity == 4

    @pytest.mark.asyncio
    async def test_list_by_user(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        p1 = await _make_product(
            session, category_id=cat.id, name="P1", price_smallest_unit=100,
        )
        p2 = await _make_product(
            session, category_id=cat.id, name="P2", price_smallest_unit=200,
        )
        await session.flush()

        repo = CartItemRepository(session)
        await repo.add_item(user_id=user.id, product_id=p1.id)
        await repo.add_item(user_id=user.id, product_id=p2.id)
        await session.flush()
        items = await repo.list_by_user(user.id)
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_remove_item(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        prod = await _make_product(
            session, category_id=cat.id, name="P", price_smallest_unit=100,
        )
        await session.flush()

        repo = CartItemRepository(session)
        item = await repo.add_item(user_id=user.id, product_id=prod.id)
        await session.flush()
        await repo.remove_item(item.id)
        await session.flush()
        items = await repo.list_by_user(user.id)
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_update_quantity(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        prod = await _make_product(
            session, category_id=cat.id, name="P", price_smallest_unit=100,
        )
        await session.flush()

        repo = CartItemRepository(session)
        item = await repo.add_item(user_id=user.id, product_id=prod.id, quantity=1)
        await session.flush()
        await repo.update_quantity(item.id, quantity=5)
        await session.flush()
        found = await repo.get(item.id)
        assert found is not None
        assert found.quantity == 5

    @pytest.mark.asyncio
    async def test_clear_cart(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        p1 = await _make_product(
            session, category_id=cat.id, name="P1", price_smallest_unit=100,
        )
        p2 = await _make_product(
            session, category_id=cat.id, name="P2", price_smallest_unit=200,
        )
        await session.flush()

        repo = CartItemRepository(session)
        await repo.add_item(user_id=user.id, product_id=p1.id)
        await repo.add_item(user_id=user.id, product_id=p2.id)
        await session.flush()
        await repo.clear_cart(user.id)
        await session.flush()
        items = await repo.list_by_user(user.id)
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_count_items(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        p1 = await _make_product(
            session, category_id=cat.id, name="P1", price_smallest_unit=100,
        )
        p2 = await _make_product(
            session, category_id=cat.id, name="P2", price_smallest_unit=200,
        )
        await session.flush()

        repo = CartItemRepository(session)
        await repo.add_item(user_id=user.id, product_id=p1.id, quantity=3)
        await repo.add_item(user_id=user.id, product_id=p2.id, quantity=2)
        await session.flush()
        total = await repo.count_items(user.id)
        assert total == 5


# ── OrderRepository ─────────────────────────────────────────────


class TestOrderRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        await session.flush()
        repo = OrderRepository(session)
        order = await repo.create(user_id=user.id)
        await session.flush()
        found = await repo.get(order.id)
        assert found is not None
        assert found.status == OrderStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_list_by_user(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        await session.flush()
        repo = OrderRepository(session)
        await repo.create(user_id=user.id)
        await repo.create(user_id=user.id)
        await session.flush()
        orders = await repo.list_by_user(user.id)
        assert len(orders) == 2

    @pytest.mark.asyncio
    async def test_update_status(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        await session.flush()
        repo = OrderRepository(session)
        order = await repo.create(user_id=user.id)
        await session.flush()
        await repo.update_status(order.id, OrderStatus.PAID)
        await session.flush()
        found = await repo.get(order.id)
        assert found is not None
        assert found.status == OrderStatus.PAID.value

    @pytest.mark.asyncio
    async def test_set_total(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        await session.flush()
        repo = OrderRepository(session)
        order = await repo.create(user_id=user.id)
        await session.flush()
        await repo.set_total(order.id, 99_000)
        await session.flush()
        found = await repo.get(order.id)
        assert found is not None
        assert found.total_smallest_unit == 99_000


# ── OrderItemRepository ─────────────────────────────────────────


class TestOrderItemRepository:
    @pytest.mark.asyncio
    async def test_create(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        prod = await _make_product(
            session, category_id=cat.id, name="Widget", price_smallest_unit=50_000,
        )
        await session.flush()
        order_repo = OrderRepository(session)
        order = await order_repo.create(user_id=user.id)
        await session.flush()

        repo = OrderItemRepository(session)
        item = await repo.create(
            order_id=order.id,
            product_id=prod.id,
            product_name="Widget",
            quantity=2,
            unit_price_smallest_unit=50_000,
        )
        await session.flush()
        assert item.order_id == order.id

    @pytest.mark.asyncio
    async def test_list_by_order(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        p1 = await _make_product(
            session, category_id=cat.id, name="A", price_smallest_unit=10,
        )
        p2 = await _make_product(
            session, category_id=cat.id, name="B", price_smallest_unit=20,
        )
        await session.flush()
        order_repo = OrderRepository(session)
        order = await order_repo.create(user_id=user.id)
        await session.flush()

        repo = OrderItemRepository(session)
        await repo.create(
            order_id=order.id,
            product_id=p1.id,
            product_name="A",
            quantity=1,
            unit_price_smallest_unit=10,
        )
        await repo.create(
            order_id=order.id,
            product_id=p2.id,
            product_name="B",
            quantity=1,
            unit_price_smallest_unit=20,
        )
        await session.flush()
        items = await repo.list_by_order(order.id)
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_bulk_create(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        cat = await _make_category(session, name="F", slug="f")
        await session.flush()
        p1 = await _make_product(
            session, category_id=cat.id, name="A", price_smallest_unit=10,
        )
        await session.flush()
        order_repo = OrderRepository(session)
        order = await order_repo.create(user_id=user.id)
        await session.flush()

        repo = OrderItemRepository(session)
        items = [
            OrderItem(
                order_id=order.id,
                product_id=p1.id,
                product_name="A",
                quantity=2,
                unit_price_smallest_unit=10,
            ),
        ]
        await repo.bulk_create(items)
        await session.flush()
        found = await repo.list_by_order(order.id)
        assert len(found) == 1


# ── PaymentRepository ───────────────────────────────────────────


class TestPaymentRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        await session.flush()
        order_repo = OrderRepository(session)
        order = await order_repo.create(user_id=user.id)
        await session.flush()

        repo = PaymentRepository(session)
        payment = await repo.create(order_id=order.id, provider="stripe")
        await session.flush()
        found = await repo.get(payment.id)
        assert found is not None
        assert found.provider == "stripe"
        assert found.status == PaymentStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_get_by_order(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        await session.flush()
        order_repo = OrderRepository(session)
        order = await order_repo.create(user_id=user.id)
        await session.flush()

        repo = PaymentRepository(session)
        await repo.create(order_id=order.id, provider="stripe")
        await repo.create(order_id=order.id, provider="yookassa")
        await session.flush()
        payments = await repo.get_by_order(order.id)
        assert len(payments) == 2

    @pytest.mark.asyncio
    async def test_update_status(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        await session.flush()
        order_repo = OrderRepository(session)
        order = await order_repo.create(user_id=user.id)
        await session.flush()

        repo = PaymentRepository(session)
        payment = await repo.create(order_id=order.id, provider="stripe")
        await session.flush()

        await repo.update_status(
            payment.id,
            PaymentStatus.SUCCESS,
            telegram_charge_id="tg_123",
            provider_charge_id="pay_abc",
        )
        await session.flush()

        found = await repo.get(payment.id)
        assert found is not None
        assert found.status == PaymentStatus.SUCCESS.value
        assert found.telegram_charge_id == "tg_123"
        assert found.provider_charge_id == "pay_abc"
