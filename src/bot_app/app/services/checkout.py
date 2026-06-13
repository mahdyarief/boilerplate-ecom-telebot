"""Checkout service — business logic for order creation, stock war protection, payments.

Every public method runs within a single ``UnitOfWork`` transaction so that
stock reservation, order creation, and cart clearing are atomic.
If *any* stock reservation fails the entire transaction is rolled back
and no stock is deducted — eliminating the "stock war" race condition.
"""

from __future__ import annotations

import logging

from aiogram.types import LabeledPrice

from ...core.config import settings
from ...core.constants import OrderStatus, PaymentStatus, WalletTransactionType
from ...core.errors import NotFoundError, StockError, WalletError
from ...infrastructure.persistence.models import Order
from ...infrastructure.persistence.uow import UnitOfWork
from ...shared.money import Money

logger = logging.getLogger(__name__)


class CheckoutService:
    """Orchestrates checkout: reserve stock → create order → send invoice → confirm."""

    def __init__(self, session_factory) -> None:  # type: ignore[valid-type]
        self._session_factory = session_factory

    # ── Order creation ─────────────────────────────────────

    async def create_order_from_cart(
        self,
        user_id: int,
        shipping_address: str,
        coupon_percent: int = 0,
    ) -> Order:
        """Convert the user's cart into an order with reserved stock.

        Steps (all inside one transaction):

        1. Read cart items
        2. Validate that every product still exists and is active
        3. **Atomically reserve** stock for every item (``reserve_stock``)
        4. Create ``Order`` + ``OrderItem`` rows
        5. Calculate and persist total (with optional coupon discount)
        6. Clear the cart

        Raises
        ------
        NotFoundError
            If the cart is empty or a product disappeared.
        StockError
            If any item's stock is insufficient (the entire transaction
            is rolled back so no partial reservation leaks).
        """
        async with UnitOfWork(self._session_factory) as uow:
            # ── 1. Read cart ────────────────────────────────
            cart_items = await uow.cart_items.list_by_user(user_id)
            if not cart_items:
                raise NotFoundError("Keranjang Anda kosong.")

            # ── 2. Read products & validate ────────────────
            product_map: dict[int, object] = {}
            for item in cart_items:
                product = await uow.products.get(item.product_id)
                if product is None or not product.is_active:
                    raise NotFoundError(
                        f"Produk {item.product_id} tidak tersedia."
                    )
                product_map[item.product_id] = product

            # ── 3. Reserve stock atomically ─────────────────
            for item in cart_items:
                reserved = await uow.products.reserve_stock(
                    item.product_id, item.quantity,
                )
                if not reserved:
                    product = product_map[item.product_id]
                    raise StockError(
                        f"Stok tidak cukup untuk {product.name}. "
                        "Silakan kurangi jumlah dan coba lagi."
                    )

            # ── 4. Create order + items ─────────────────────
            order = await uow.orders.create(
                user_id=user_id,
                shipping_address=shipping_address,
            )
            await uow.session.flush()

            gross_total = 0
            for item in cart_items:
                product = product_map[item.product_id]
                await uow.order_items.create(
                    order_id=order.id,
                    product_id=item.product_id,
                    product_name=product.name,
                    quantity=item.quantity,
                    unit_price_smallest_unit=product.price_smallest_unit,
                )
                gross_total += product.price_smallest_unit * item.quantity

            # ── 5. Apply coupon discount & persist total ─────
            total = gross_total
            if coupon_percent > 0:
                from ...app.services.pricing import apply_coupon_discount
                discount = apply_coupon_discount(
                    Money(gross_total, settings.CURRENCY),
                    coupon_percent,
                )
                total = gross_total - discount.amount_minor

            await uow.orders.set_total(order.id, total)

            # ── 6. Clear cart ──────────────────────────────
            await uow.cart_items.clear_cart(user_id)

            # Re-read order with items for the caller
            order = await uow.orders.get(order.id)
            return order  # type: ignore[return-value]

    # ── Pre-checkout verification ──────────────────────────

    async def verify_pre_checkout(
        self,
        order_id: int,
    ) -> tuple[bool, str]:
        """Final verification before the payment provider processes the charge.

        Returns ``(True, "")`` if everything is fine or
        ``(False, error_message)`` to reject the payment.
        """
        async with UnitOfWork(self._session_factory) as uow:
            order = await uow.orders.get(order_id)
            if order is None:
                return False, "Pesanan tidak ditemukan."
            if order.status not in (
                OrderStatus.PENDING.value,
                OrderStatus.AWAITING_PAYMENT.value,
            ):
                return False, "Pesanan sudah diproses atau dibatalkan."

            # Re-verify stock (defence in depth)
            items = await uow.order_items.list_by_order(order_id)
            for item in items:
                product = await uow.products.get(item.product_id)
                if product is None or product.stock < 0:
                    return False, f"Stok {item.product_name} tidak tersedia."

        return True, ""

    # ── Payment confirmation ───────────────────────────────

    async def confirm_payment(
        self,
        order_id: int,
        telegram_charge_id: str,
        provider_charge_id: str,
        *,
        provider_name: str = "provider_token",
    ) -> None:
        """Mark order as PAID and create a successful Payment record.

        Stock was already decremented in :meth:`create_order_from_cart`,
        so no stock mutation happens here — only the bookkeeping changes.

        Parameters
        ----------
        order_id : int
            The order to confirm.
        telegram_charge_id : str
            Telegram charge ID (or payment identifier for off-platform).
        provider_charge_id : str
            Provider charge ID (or payment identifier for off-platform).
        provider_name : str
            Name of the provider ("provider_token", "qris", "pakasir").
        """
        async with UnitOfWork(self._session_factory) as uow:
            order = await uow.orders.get(order_id)
            if order is None:
                raise NotFoundError(f"Order {order_id} not found")

            await uow.orders.update_status(order_id, OrderStatus.PAID)

            # Find the existing PENDING payment record for this order/provider
            existing_payment = await uow.payments.get_pending_by_order(order_id)

            if existing_payment is not None:
                # Update the existing record to SUCCESS
                await uow.payments.update_status(
                    existing_payment.id,
                    PaymentStatus.SUCCESS,
                    telegram_charge_id=telegram_charge_id,
                    provider_charge_id=provider_charge_id,
                )
            else:
                # Create a new payment record (Telegram Payments API path)
                payment = await uow.payments.create(
                    order_id=order_id,
                    provider=provider_name,
                )
                await uow.session.flush()
                await uow.payments.update_status(
                    payment.id,
                    PaymentStatus.SUCCESS,
                    telegram_charge_id=telegram_charge_id,
                    provider_charge_id=provider_charge_id,
                )

    # ── Order cancellation ─────────────────────────────────

    async def cancel_order(self, order_id: int, user_id: int) -> bool:
        """Cancel an order and release reserved stock.

        Returns ``True`` if the order was cancelled, ``False`` if it
        could not be cancelled (already paid / not owned by *user_id*).
        """
        async with UnitOfWork(self._session_factory) as uow:
            order = await uow.orders.get(order_id)
            if order is None or order.user_id != user_id:
                return False
            if order.status not in (
                OrderStatus.PENDING.value,
                OrderStatus.AWAITING_PAYMENT.value,
            ):
                return False

            # Release stock for each item
            items = await uow.order_items.list_by_order(order_id)
            for item in items:
                await uow.products.release_stock(item.product_id, item.quantity)

            await uow.orders.update_status(order_id, OrderStatus.CANCELLED)
            return True

    # ── Wallet payment ────────────────────────────────────────

    async def pay_with_wallet(
        self,
        order_id: int,
        user_id: int,
    ) -> int:
        """Pay for an order using the user's wallet (saldo).

        This is an atomic operation that:
        1. Verifies the order belongs to the user and is awaiting payment
        2. Debits the wallet balance (with ``WHERE balance >= amount`` guard)
        3. Creates a Payment record with provider="wallet"
        4. Updates the order status to PAID

        Returns the new wallet balance after payment.

        Raises
        ------
        NotFoundError
            If the order does not exist or doesn't belong to the user.
        WalletError
            If the wallet has insufficient balance.
        """
        async with UnitOfWork(self._session_factory) as uow:
            order = await uow.orders.get(order_id)
            if order is None or order.user_id != user_id:
                raise NotFoundError(f"Pesanan #{order_id} tidak ditemukan.")

            if order.status not in (
                OrderStatus.PENDING.value,
                OrderStatus.AWAITING_PAYMENT.value,
            ):
                raise NotFoundError(
                    f"Pesanan #{order_id} tidak dapat dibayar (status: {order.status})."
                )

            amount = order.total_smallest_unit

            # Get or create wallet
            wallet = await uow.wallets.get_or_create(user_id)

            # Atomic debit with balance guard
            try:
                tx = await uow.wallets.debit(
                    wallet.id,
                    amount,
                    transaction_type=WalletTransactionType.PAYMENT.value,
                    order_id=order_id,
                    note=f"Pembayaran pesanan #{order_id}",
                )
            except ValueError:
                raise WalletError(
                    f"Saldo tidak cukup. Saldo Anda: {wallet.balance_smallest_unit}, "
                    f"dibutuhkan: {amount}."
                )

            # Create a Payment record with provider="wallet"
            await uow.payments.create(
                order_id=order_id,
                provider="wallet",
            )
            # Flush to get the payment record ID
            await uow.session.flush()

            # Mark the payment as SUCCESS
            pending = await uow.payments.get_pending_by_order(order_id)
            if pending is not None:
                await uow.payments.update_status(
                    pending.id,
                    PaymentStatus.SUCCESS,
                    telegram_charge_id=f"wallet_{order_id}_{tx.id}",
                    provider_charge_id=f"wallet_{order_id}_{tx.id}",
                )

            # Update order status to PAID
            await uow.orders.update_status(order_id, OrderStatus.PAID)

            logger.info(
                "wallet payment confirmed: order=%d user=%d amount=%d balance_after=%d",
                order_id, user_id, amount, tx.balance_after,
            )

            return tx.balance_after

    # ── Wallet refund on cancellation ─────────────────────────

    async def cancel_order_and_refund_wallet(
        self,
        order_id: int,
        user_id: int,
    ) -> tuple[bool, int]:
        """Cancel an order, release stock, and refund wallet if it was paid via wallet.

        Returns ``(cancelled, refunded_amount)`` where ``refunded_amount``
        is 0 if the order was not paid via wallet.
        """
        async with UnitOfWork(self._session_factory) as uow:
            order = await uow.orders.get(order_id)
            if order is None or order.user_id != user_id:
                return False, 0

            if order.status not in (
                OrderStatus.PENDING.value,
                OrderStatus.AWAITING_PAYMENT.value,
                OrderStatus.PAID.value,
            ):
                return False, 0

            refunded_amount = 0

            # If the order was paid via wallet, refund it
            if order.status == OrderStatus.PAID.value:
                payments = await uow.payments.get_by_order(order_id)
                wallet_payment = None
                for p in payments:
                    if p.provider == "wallet" and p.status == PaymentStatus.SUCCESS.value:
                        wallet_payment = p
                        break

                if wallet_payment is not None:
                    wallet = await uow.wallets.get_or_create(user_id)
                    await uow.wallets.credit(
                        wallet.id,
                        order.total_smallest_unit,
                        transaction_type=WalletTransactionType.REFUND.value,
                        order_id=order_id,
                        note=f"Refund pembatalan pesanan #{order_id}",
                    )
                    refunded_amount = order.total_smallest_unit

                    # Mark the original payment as refunded
                    await uow.payments.update_status(
                        wallet_payment.id,
                        PaymentStatus.REFUNDED,
                    )

            # Release stock for each item
            items = await uow.order_items.list_by_order(order_id)
            for item in items:
                await uow.products.release_stock(item.product_id, item.quantity)

            await uow.orders.update_status(order_id, OrderStatus.CANCELLED)
            return True, refunded_amount

    # ── Expired reservation reaper ────────────────────────

    async def release_expired_reservations(self) -> int:
        """Release stock for orders that exceeded the reservation TTL.

        Returns the number of orders that were expired.
        Called periodically or on-demand (e.g. before checkout).
        """
        ttl_minutes = settings.ORDER_RESERVATION_TTL
        count = 0

        async with UnitOfWork(self._session_factory) as uow:
            expired = await uow.orders.list_pending_expired(ttl_minutes)

            for order in expired:
                items = await uow.order_items.list_by_order(order.id)
                for item in items:
                    await uow.products.release_stock(item.product_id, item.quantity)
                await uow.orders.update_status(order.id, OrderStatus.CANCELLED)
                count += 1
                logger.info(
                    "expired order %d cancelled, stock released", order.id,
                )

        return count

    # ── Invoice helpers ────────────────────────────────────

    @staticmethod
    def build_invoice_prices(order_items: list) -> list[LabeledPrice]:
        """Build ``LabeledPrice`` list from order items for ``send_invoice``.

        Each item becomes one :class:`LabeledPrice` showing the line total
        (unit price × quantity).
        """
        prices: list[LabeledPrice] = []
        for item in order_items:
            prices.append(
                LabeledPrice(
                    label=f"{item.product_name} x{item.quantity}",
                    amount=item.unit_price_smallest_unit * item.quantity,
                )
            )
        return prices

    @staticmethod
    def build_invoice_description(order_items: list) -> str:
        """Human-readable description for the Telegram invoice."""
        lines: list[str] = []
        for item in order_items:
            unit_price = Money(item.unit_price_smallest_unit, settings.CURRENCY)
            lines.append(f"• {item.product_name} x{item.quantity} — {unit_price.format()}")
        return "\n".join(lines)
