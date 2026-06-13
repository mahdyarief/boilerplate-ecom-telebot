"""Unit of Work — scoped transaction boundary around repositories.

Each ``UnitOfWork`` owns a single ``AsyncSession`` and exposes all
repository instances through properties.  On ``__aenter__`` a session is
opened; on ``__aexit__`` the session is committed / rolled-back and
closed.  This prevents repositories from leaking transaction management
into the handler layer.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .repositories import (
    CartItemRepository,
    CategoryRepository,
    CouponRepository,
    OrderItemRepository,
    OrderRepository,
    PaymentRepository,
    ProductImageRepository,
    ProductRepository,
    UserRepository,
    WalletRepository,
)


class UnitOfWork:
    """Async context-manager that provides a scoped set of repositories.

    Usage::

        async with UnitOfWork(session_factory) as uow:
            user = await uow.users.get_or_create(42)
            # ... more work ...
            # commit happens automatically on exit (or rollback on error)

    Repositories are accessed as attributes:

    * ``uow.users``  → :class:`UserRepository`
    * ``uow.categories`` → :class:`CategoryRepository`
    * ``uow.products`` → :class:`ProductRepository`
    * ``uow.cart_items`` → :class:`CartItemRepository`
    * ``uow.orders`` → :class:`OrderRepository`
    * ``uow.order_items`` → :class:`OrderItemRepository`
    * ``uow.payments`` → :class:`PaymentRepository`
    * ``uow.coupons``   → :class:`CouponRepository`
    * ``uow.product_images`` → :class:`ProductImageRepository`
    * ``uow.wallets``   → :class:`WalletRepository`
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._repos: SimpleNamespace | None = None

    # ── context manager ────────────────────────────────────

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self._repos = SimpleNamespace(
            users=UserRepository(self._session),
            categories=CategoryRepository(self._session),
            products=ProductRepository(self._session),
            cart_items=CartItemRepository(self._session),
            orders=OrderRepository(self._session),
            order_items=OrderItemRepository(self._session),
            payments=PaymentRepository(self._session),
            coupons=CouponRepository(self._session),
            product_images=ProductImageRepository(self._session),
            wallets=WalletRepository(self._session),
        )
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        assert self._session is not None  # for type-checker
        try:
            if exc_type is not None:
                await self._session.rollback()
            else:
                await self._session.commit()
        finally:
            await self._session.close()
            self._session = None
            self._repos = None

    # ── repository accessors ───────────────────────────────

    @property
    def session(self) -> AsyncSession:
        """The current ``AsyncSession`` (available inside the context)."""
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active — use it as a context manager")
        return self._session

    @property
    def users(self) -> UserRepository:
        if self._repos is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._repos.users

    @property
    def categories(self) -> CategoryRepository:
        if self._repos is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._repos.categories

    @property
    def products(self) -> ProductRepository:
        if self._repos is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._repos.products

    @property
    def cart_items(self) -> CartItemRepository:
        if self._repos is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._repos.cart_items

    @property
    def orders(self) -> OrderRepository:
        if self._repos is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._repos.orders

    @property
    def order_items(self) -> OrderItemRepository:
        if self._repos is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._repos.order_items

    @property
    def payments(self) -> PaymentRepository:
        if self._repos is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._repos.payments

    @property
    def coupons(self) -> CouponRepository:
        if self._repos is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._repos.coupons

    @property
    def product_images(self) -> ProductImageRepository:
        if self._repos is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._repos.product_images

    @property
    def wallets(self) -> WalletRepository:
        if self._repos is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._repos.wallets
