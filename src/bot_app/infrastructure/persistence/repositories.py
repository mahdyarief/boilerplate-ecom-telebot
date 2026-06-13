"""Async repository classes — one per aggregate root.

Every repository method receives the database session through the
constructor so that callers control the transaction boundary
(via a ``async_sessionmaker`` or explicit session management).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.constants import OrderStatus, PaymentStatus, WalletTransactionType
from .models import (
    CartItem,
    Category,
    Coupon,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductImage,
    User,
    Wallet,
    WalletTransaction,
)

# ── User ───────────────────────────────────────────────────────


class UserRepository:
    """Data access for the ``users`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: int, *, language: str = "id") -> User:
        """Return existing user or insert a new one and return it."""
        user = await self.get(user_id)
        if user is not None:
            return user
        user = User(id=user_id, language=language)
        self._session.add(user)
        await self._session.flush()
        return user

    async def set_language(self, user_id: int, language: str) -> None:
        stmt = update(User).where(User.id == user_id).values(language=language)
        await self._session.execute(stmt)

    async def toggle_admin(self, user_id: int, *, is_admin: bool) -> None:
        stmt = update(User).where(User.id == user_id).values(is_admin=is_admin)
        await self._session.execute(stmt)

    async def list_admins(self) -> Sequence[User]:
        stmt = select(User).where(User.is_admin.is_(True))
        result = await self._session.execute(stmt)
        return result.scalars().all()


# ── Category ───────────────────────────────────────────────────


class CategoryRepository:
    """Data access for the ``categories`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, category_id: int) -> Category | None:
        stmt = select(Category).where(Category.id == category_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Category | None:
        stmt = select(Category).where(Category.slug == slug)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(
        self,
        *,
        parent_id: int | None = None,
    ) -> Sequence[Category]:
        stmt = select(Category).where(Category.is_active.is_(True))
        if parent_id is not None:
            stmt = stmt.where(Category.parent_id == parent_id)
        else:
            stmt = stmt.where(Category.parent_id.is_(None))
        stmt = stmt.order_by(Category.position, Category.id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create(
        self,
        *,
        name: str,
        slug: str,
        parent_id: int | None = None,
        position: int = 0,
    ) -> Category:
        category = Category(
            name=name,
            slug=slug,
            parent_id=parent_id,
            position=position,
        )
        self._session.add(category)
        await self._session.flush()
        return category

    async def update(
        self,
        category_id: int,
        *,
        name: str | None = None,
        slug: str | None = None,
        position: int | None = None,
        is_active: bool | None = None,
    ) -> None:
        values: dict = {}
        if name is not None:
            values["name"] = name
        if slug is not None:
            values["slug"] = slug
        if position is not None:
            values["position"] = position
        if is_active is not None:
            values["is_active"] = is_active
        if not values:
            return
        stmt = update(Category).where(Category.id == category_id).values(**values)
        await self._session.execute(stmt)

    async def toggle_active(self, category_id: int, *, is_active: bool) -> None:
        await self.update(category_id, is_active=is_active)


# ── Product ────────────────────────────────────────────────────


class ProductRepository:
    """Data access for the ``products`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, product_id: int) -> Product | None:
        stmt = select(Product).where(Product.id == product_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_category(
        self,
        category_id: int,
        *,
        active_only: bool = True,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[Product]:
        stmt = select(Product).where(Product.category_id == category_id)
        if active_only:
            stmt = stmt.where(Product.is_active.is_(True))
        stmt = stmt.order_by(Product.id).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create(
        self,
        *,
        category_id: int,
        name: str,
        price_smallest_unit: int,
        description: str | None = None,
        stock: int = 0,
    ) -> Product:
        product = Product(
            category_id=category_id,
            name=name,
            description=description,
            price_smallest_unit=price_smallest_unit,
            stock=stock,
        )
        self._session.add(product)
        await self._session.flush()
        return product

    async def update(
        self,
        product_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        price_smallest_unit: int | None = None,
        stock: int | None = None,
        is_active: bool | None = None,
    ) -> None:
        values: dict = {}
        if name is not None:
            values["name"] = name
        if description is not None:
            values["description"] = description
        if price_smallest_unit is not None:
            values["price_smallest_unit"] = price_smallest_unit
        if stock is not None:
            values["stock"] = stock
        if is_active is not None:
            values["is_active"] = is_active
        if not values:
            return
        stmt = update(Product).where(Product.id == product_id).values(**values)
        await self._session.execute(stmt)

    async def update_stock(self, product_id: int, delta: int) -> None:
        """Atomically adjust stock by *delta* (negative to decrement)."""
        stmt = update(Product).where(Product.id == product_id).values(stock=Product.stock + delta)
        await self._session.execute(stmt)

    async def reserve_stock(self, product_id: int, quantity: int) -> bool:
        """Atomically decrement stock by *quantity*.

        Uses ``WHERE stock >= quantity`` to guarantee the stock never
        goes negative.  Returns ``True`` if the row was updated (reservation
        succeeded), ``False`` if stock was insufficient.

        This is the core of the **StockWar Protection** — the database
        serialises concurrent reservations so that two checkouts that
        together would exceed available stock cannot both succeed.
        """
        stmt = (
            update(Product)
            .where(Product.id == product_id, Product.stock >= quantity)
            .values(stock=Product.stock - quantity)
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0

    async def release_stock(self, product_id: int, quantity: int) -> None:
        """Increment stock back (un-reserve).

        Called when an order is cancelled or a reservation expires so
        that the stock becomes available for other buyers again.
        """
        stmt = (
            update(Product)
            .where(Product.id == product_id)
            .values(stock=Product.stock + quantity)
        )
        await self._session.execute(stmt)

    async def confirm_stock(self, product_id: int, quantity: int) -> None:
        """Mark a stock reservation as permanently sold.

        In the current implementation the reservation *already* decremented
        the stock atomically in :meth:`reserve_stock`, so this is a **no-op**.
        The method exists so that a future "soft-reservation" model
        (e.g. ``stock_reserved`` vs ``stock_available``) can be swapped in
        without changing the service layer.
        """
        # no-op: stock was decremented at reserve time

    async def toggle_active(self, product_id: int, *, is_active: bool) -> None:
        await self.update(product_id, is_active=is_active)


# ── CartItem ───────────────────────────────────────────────────


class CartItemRepository:
    """Data access for the ``cart_items`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: int) -> Sequence[CartItem]:
        stmt = select(CartItem).where(CartItem.user_id == user_id).order_by(CartItem.id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get(self, cart_item_id: int) -> CartItem | None:
        stmt = select(CartItem).where(CartItem.id == cart_item_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_user_and_product(
        self,
        user_id: int,
        product_id: int,
    ) -> CartItem | None:
        stmt = select(CartItem).where(
            CartItem.user_id == user_id,
            CartItem.product_id == product_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_item(
        self,
        *,
        user_id: int,
        product_id: int,
        quantity: int = 1,
    ) -> CartItem:
        """Add a product to the cart.

        If the (user_id, product_id) pair already exists the quantity is
        incremented instead.
        """
        existing = await self.find_by_user_and_product(user_id, product_id)
        if existing is not None:
            existing.quantity += quantity
            await self._session.flush()
            return existing

        item = CartItem(user_id=user_id, product_id=product_id, quantity=quantity)
        self._session.add(item)
        await self._session.flush()
        return item

    async def remove_item(self, cart_item_id: int) -> None:
        stmt = delete(CartItem).where(CartItem.id == cart_item_id)
        await self._session.execute(stmt)

    async def update_quantity(self, cart_item_id: int, quantity: int) -> None:
        stmt = update(CartItem).where(CartItem.id == cart_item_id).values(quantity=quantity)
        await self._session.execute(stmt)

    async def clear_cart(self, user_id: int) -> None:
        stmt = delete(CartItem).where(CartItem.user_id == user_id)
        await self._session.execute(stmt)

    async def count_items(self, user_id: int) -> int:
        stmt = select(func.coalesce(func.sum(CartItem.quantity), 0)).where(
            CartItem.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())


# ── Order ──────────────────────────────────────────────────────


class OrderRepository:
    """Data access for the ``orders`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, order_id: int) -> Order | None:
        stmt = select(Order).where(Order.id == order_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 10,
    ) -> Sequence[Order]:
        stmt = (
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create(
        self,
        *,
        user_id: int,
        shipping_address: str | None = None,
    ) -> Order:
        order = Order(
            user_id=user_id,
            status=OrderStatus.PENDING.value,
            shipping_address=shipping_address,
        )
        self._session.add(order)
        await self._session.flush()
        return order

    async def update_status(self, order_id: int, status: OrderStatus) -> None:
        stmt = update(Order).where(Order.id == order_id).values(status=status.value)
        await self._session.execute(stmt)

    async def set_total(self, order_id: int, total_smallest_unit: int) -> None:
        stmt = (
            update(Order)
            .where(Order.id == order_id)
            .values(total_smallest_unit=total_smallest_unit)
        )
        await self._session.execute(stmt)

    async def list_pending_expired(self, ttl_minutes: int) -> Sequence[Order]:
        """Return orders still in PENDING / AWAITING_PAYMENT older than *ttl_minutes*.

        Used by the reservation-reaper to release stock for orders that
        never completed payment within the configured TTL.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=ttl_minutes)
        stmt = (
            select(Order)
            .where(
                Order.status.in_(
                    [OrderStatus.PENDING.value, OrderStatus.AWAITING_PAYMENT.value]
                ),
                Order.created_at < cutoff,
            )
            .order_by(Order.id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()


# ── OrderItem ──────────────────────────────────────────────────


class OrderItemRepository:
    """Data access for the ``order_items`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_order(self, order_id: int) -> Sequence[OrderItem]:
        stmt = select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def bulk_create(self, items: list[OrderItem]) -> None:
        self._session.add_all(items)
        await self._session.flush()

    async def create(
        self,
        *,
        order_id: int,
        product_id: int,
        product_name: str,
        quantity: int,
        unit_price_smallest_unit: int,
    ) -> OrderItem:
        item = OrderItem(
            order_id=order_id,
            product_id=product_id,
            product_name=product_name,
            quantity=quantity,
            unit_price_smallest_unit=unit_price_smallest_unit,
        )
        self._session.add(item)
        await self._session.flush()
        return item


# ── Payment ────────────────────────────────────────────────────


class PaymentRepository:
    """Data access for the ``payments`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, payment_id: int) -> Payment | None:
        stmt = select(Payment).where(Payment.id == payment_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_order(self, order_id: int) -> Sequence[Payment]:
        stmt = select(Payment).where(Payment.order_id == order_id).order_by(Payment.id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_identifier(self, payment_identifier: str) -> Payment | None:
        """Look up a pending payment by its ``payment_identifier``."""
        stmt = select(Payment).where(
            Payment.payment_identifier == payment_identifier,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_by_order(self, order_id: int) -> Payment | None:
        """Return the most recent PENDING payment for an order, or None."""
        stmt = (
            select(Payment)
            .where(
                Payment.order_id == order_id,
                Payment.status == PaymentStatus.PENDING.value,
            )
            .order_by(Payment.id.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        order_id: int,
        provider: str,
        payment_identifier: str | None = None,
        unique_code: int = 0,
        final_amount: int = 0,
        qris_payload: str | None = None,
        payment_url: str | None = None,
    ) -> Payment:
        payment = Payment(
            order_id=order_id,
            provider=provider,
            status=PaymentStatus.PENDING.value,
            payment_identifier=payment_identifier,
            unique_code=unique_code,
            final_amount=final_amount,
            qris_payload=qris_payload,
            payment_url=payment_url,
        )
        self._session.add(payment)
        await self._session.flush()
        return payment

    async def update_invoice_data(
        self,
        payment_id: int,
        *,
        payment_identifier: str | None = None,
        unique_code: int | None = None,
        final_amount: int | None = None,
        qris_payload: str | None = None,
        payment_url: str | None = None,
    ) -> None:
        """Update a payment record with QRIS / Pakasir invoice data."""
        values: dict = {}
        if payment_identifier is not None:
            values["payment_identifier"] = payment_identifier
        if unique_code is not None:
            values["unique_code"] = unique_code
        if final_amount is not None:
            values["final_amount"] = final_amount
        if qris_payload is not None:
            values["qris_payload"] = qris_payload
        if payment_url is not None:
            values["payment_url"] = payment_url
        if not values:
            return
        stmt = update(Payment).where(Payment.id == payment_id).values(**values)
        await self._session.execute(stmt)

    async def update_status(
        self,
        payment_id: int,
        status: PaymentStatus,
        *,
        telegram_charge_id: str | None = None,
        provider_charge_id: str | None = None,
    ) -> None:
        values: dict = {"status": status.value}
        if telegram_charge_id is not None:
            values["telegram_charge_id"] = telegram_charge_id
        if provider_charge_id is not None:
            values["provider_charge_id"] = provider_charge_id
        stmt = update(Payment).where(Payment.id == payment_id).values(**values)
        await self._session.execute(stmt)


# ── Coupon ────────────────────────────────────────────────────


class CouponRepository:
    """Data access for the ``coupons`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, coupon_id: int) -> Coupon | None:
        stmt = select(Coupon).where(Coupon.id == coupon_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Coupon | None:
        stmt = select(Coupon).where(Coupon.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        active_only: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[Coupon]:
        stmt = select(Coupon).order_by(Coupon.id.desc())
        if active_only:
            stmt = stmt.where(Coupon.is_active.is_(True))
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create(
        self,
        *,
        code: str,
        discount_percent: int,
        max_uses: int | None = None,
        expires_at: datetime | None = None,
    ) -> Coupon:
        coupon = Coupon(
            code=code.upper().strip(),
            discount_percent=discount_percent,
            max_uses=max_uses,
            expires_at=expires_at,
        )
        self._session.add(coupon)
        await self._session.flush()
        return coupon

    async def increment_used(self, coupon_id: int) -> None:
        """Atomically increment used_count by 1."""
        stmt = (
            update(Coupon)
            .where(Coupon.id == coupon_id)
            .values(used_count=Coupon.used_count + 1)
        )
        await self._session.execute(stmt)

    async def toggle_active(self, coupon_id: int, *, is_active: bool) -> None:
        stmt = update(Coupon).where(Coupon.id == coupon_id).values(is_active=is_active)
        await self._session.execute(stmt)

    async def delete(self, coupon_id: int) -> None:
        """Hard-delete a coupon."""
        stmt = delete(Coupon).where(Coupon.id == coupon_id)
        await self._session.execute(stmt)


# ── ProductImage ──────────────────────────────────────────────


class ProductImageRepository:
    """Data access for the ``product_images`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, image_id: int) -> ProductImage | None:
        stmt = select(ProductImage).where(ProductImage.id == image_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_product(
        self,
        product_id: int,
        *,
        offset: int = 0,
        limit: int = 10,
    ) -> Sequence[ProductImage]:
        stmt = (
            select(ProductImage)
            .where(ProductImage.product_id == product_id)
            .order_by(ProductImage.position, ProductImage.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_cover(self, product_id: int) -> ProductImage | None:
        """Get the cover image for a product (first cover, or first image)."""
        stmt = (
            select(ProductImage)
            .where(ProductImage.product_id == product_id, ProductImage.is_cover.is_(True))
            .order_by(ProductImage.position)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        cover = result.scalar_one_or_none()
        if cover is not None:
            return cover
        # Fallback: return first image
        stmt = (
            select(ProductImage)
            .where(ProductImage.product_id == product_id)
            .order_by(ProductImage.position, ProductImage.id)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        product_id: int,
        file_id: str,
        position: int = 0,
        is_cover: bool = False,
    ) -> ProductImage:
        image = ProductImage(
            product_id=product_id,
            file_id=file_id,
            position=position,
            is_cover=is_cover,
        )
        self._session.add(image)
        await self._session.flush()
        return image

    async def set_cover(self, image_id: int) -> None:
        """Set an image as the cover and unset any existing cover for the same product.

        Must be called within a session that has the product's images loaded.
        """
        image = await self.get(image_id)
        if image is None:
            return
        # Unset all covers for this product
        stmt = (
            update(ProductImage)
            .where(ProductImage.product_id == image.product_id)
            .values(is_cover=False)
        )
        await self._session.execute(stmt)
        # Set the target image as cover
        stmt = update(ProductImage).where(ProductImage.id == image_id).values(is_cover=True)
        await self._session.execute(stmt)

    async def delete(self, image_id: int) -> None:
        stmt = delete(ProductImage).where(ProductImage.id == image_id)
        await self._session.execute(stmt)

    async def set_position(self, image_id: int, position: int) -> None:
        stmt = (
            update(ProductImage)
            .where(ProductImage.id == image_id)
            .values(position=position)
        )
        await self._session.execute(stmt)


# ── Wallet ────────────────────────────────────────────────────


class WalletRepository:
    """Data access for the ``wallets`` and ``wallet_transactions`` tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Wallet ──────────────────────────────────────────────

    async def get_by_user(self, user_id: int) -> Wallet | None:
        stmt = select(Wallet).where(Wallet.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: int) -> Wallet:
        """Return existing wallet or create one with zero balance."""
        wallet = await self.get_by_user(user_id)
        if wallet is not None:
            return wallet
        wallet = Wallet(user_id=user_id, balance_smallest_unit=0)
        self._session.add(wallet)
        await self._session.flush()
        return wallet

    async def credit(
        self,
        wallet_id: int,
        amount: int,
        *,
        transaction_type: str = WalletTransactionType.TOP_UP.value,
        order_id: int | None = None,
        note: str | None = None,
    ) -> WalletTransaction:
        """Add *amount* to the wallet and create a transaction record.

        Parameters
        ----------
        wallet_id : int
            The wallet to credit.
        amount : int
            Amount in smallest currency unit (must be > 0).
        transaction_type : str
            One of ``WalletTransactionType`` values.
        order_id : int | None
            Related order (if applicable).
        note : str | None
            Human-readable note.

        Returns
        -------
        WalletTransaction
            The created transaction record.
        """
        if amount <= 0:
            raise ValueError("Credit amount must be > 0")

        # Atomically increment balance using SQL expression
        stmt = (
            update(Wallet)
            .where(Wallet.id == wallet_id)
            .values(balance_smallest_unit=Wallet.balance_smallest_unit + amount)
        )
        await self._session.execute(stmt)

        # Read the updated balance
        stmt = select(Wallet).where(Wallet.id == wallet_id)
        result = await self._session.execute(stmt)
        wallet = result.scalar_one()

        tx = WalletTransaction(
            wallet_id=wallet_id,
            transaction_type=transaction_type,
            amount_smallest_unit=amount,
            balance_after=wallet.balance_smallest_unit,
            order_id=order_id,
            note=note,
        )
        self._session.add(tx)
        await self._session.flush()
        return tx

    async def debit(
        self,
        wallet_id: int,
        amount: int,
        *,
        transaction_type: str = WalletTransactionType.PAYMENT.value,
        order_id: int | None = None,
        note: str | None = None,
    ) -> WalletTransaction:
        """Subtract *amount* from the wallet atomically.

        Uses ``WHERE balance >= amount`` to guarantee the balance never
        goes negative.  Returns the transaction record on success.

        Raises
        ------
        ValueError
            If the wallet has insufficient balance.
        """
        if amount <= 0:
            raise ValueError("Debit amount must be > 0")

        # Atomically decrement balance with guard
        stmt = (
            update(Wallet)
            .where(Wallet.id == wallet_id, Wallet.balance_smallest_unit >= amount)
            .values(balance_smallest_unit=Wallet.balance_smallest_unit - amount)
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            raise ValueError("Insufficient wallet balance")

        # Read the updated balance
        stmt = select(Wallet).where(Wallet.id == wallet_id)
        result = await self._session.execute(stmt)
        wallet = result.scalar_one()

        tx = WalletTransaction(
            wallet_id=wallet_id,
            transaction_type=transaction_type,
            amount_smallest_unit=-amount,  # negative for debit
            balance_after=wallet.balance_smallest_unit,
            order_id=order_id,
            note=note,
        )
        self._session.add(tx)
        await self._session.flush()
        return tx

    # ── Transactions ───────────────────────────────────────

    async def list_transactions(
        self,
        wallet_id: int,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[WalletTransaction]:
        stmt = (
            select(WalletTransaction)
            .where(WalletTransaction.wallet_id == wallet_id)
            .order_by(WalletTransaction.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
