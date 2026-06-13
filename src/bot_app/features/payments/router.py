"""Payments router — pre_checkout_query + successful_payment + off-platform handlers.

These handlers implement both payment lifecycles:

**Telegram Payments API lifecycle:**

1. ``pre_checkout_query`` — Telegram asks the bot to confirm the payment
   can proceed.  We verify stock & order status and answer OK/Fail.
2. ``successful_payment`` — Telegram confirms the user paid.  We mark the
   order as PAID, create a Payment record, and send a receipt message.

**Off-platform (QRIS/Pakasir) lifecycle:**

1. ``pay:check:<order_id>`` — User manually checks payment status.
   For Pakasir, we query the gateway. For QRIS, we check order status
   (updated by webhook or admin).
2. ``pay:cancel:<order_id>`` — User cancels the pending payment,
   releases stock, and cancels the order.

Both Telegram-native handlers are **outside** the checkout FSM — Telegram
sends them as standalone updates regardless of FSM state.

Callback-data schema:

* ``pay:check:<order_id>``  — check off-platform payment status (handled in checkout router)
* ``pay:cancel:<order_id>`` — cancel off-platform payment (handled in checkout router)
"""

from __future__ import annotations

import logging

from aiogram import F, Router, types

from ...app.services.checkout import CheckoutService
from ...core.config import settings
from ...core.errors import NotFoundError
from ...infrastructure.persistence.uow import UnitOfWork
from ..checkout.texts import fmt_payment_failed, fmt_payment_success

logger = logging.getLogger(__name__)

router = Router(name="payments")


# ── Low-stock notification helper (Phase 6) ──────────────


async def _notify_low_stock(bot, session_factory) -> None:  # type: ignore[valid-type]
    """Check all products and notify admins if any are below the threshold.

    Called after a successful payment to proactively alert admins of
    products running low on stock.
    """
    threshold = settings.LOW_STOCK_THRESHOLD
    if threshold <= 0:
        return

    try:
        from sqlalchemy import select

        from ...infrastructure.persistence.models import Product

        async with UnitOfWork(session_factory) as uow:
            stmt = (
                select(Product)
                .where(
                    Product.is_active.is_(True),
                    Product.stock <= threshold,
                    Product.stock >= 0,
                )
                .order_by(Product.stock)
            )
            result = await uow.session.execute(stmt)
            low_stock_products = list(result.scalars().all())

        if not low_stock_products:
            return

        from ...shared.money import Money
        lines = ["⚠️ **Stok Rendah!**\n"]
        for p in low_stock_products:
            price = Money(p.price_smallest_unit, settings.CURRENCY)
            lines.append(f"📦 {p.name} — {price.format()} (stok: {p.stock})")

        text = "\n".join(lines)

        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(chat_id=admin_id, text=text)
            except Exception as exc:
                logger.warning("low_stock_notify failed for admin %d: %s", admin_id, exc)
    except Exception as exc:
        logger.error("low_stock_check error: %s", exc)


# ── Pre-checkout query (Telegram Payments API only) ──────


@router.pre_checkout_query()
async def pre_checkout_handler(
    pre_checkout: types.PreCheckoutQuery,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Verify that the order is still valid before the payment is processed.

    This is Telegram's second-chance verification — the bot can still
    reject the payment here even after the invoice was sent.

    Only fires when using the Telegram Payments API (PROVIDER_TOKEN).
    """
    payload = pre_checkout.invoice_payload
    if not payload or not payload.isdigit():
        await pre_checkout.answer(ok=False, error_message="Pesanan tidak valid.")
        return

    order_id = int(payload)
    checkout = CheckoutService(session_factory)

    ok, error_message = await checkout.verify_pre_checkout(order_id)

    if ok:
        await pre_checkout.answer(ok=True)
    else:
        await pre_checkout.answer(ok=False, error_message=error_message)


# ── Successful payment (Telegram Payments API only) ──────


@router.message(F.successful_payment)
async def successful_payment_handler(
    message: types.Message,
    state,  # type: ignore[valid-type]
    session_factory,  # type: ignore[valid-type]
) -> None:
    """User successfully completed payment — confirm the order.

    Reads the ``invoice_payload`` (which we set to the order_id) and
    the charge IDs from Telegram's payment provider.

    Only fires when using the Telegram Payments API (PROVIDER_TOKEN).
    """
    payment = message.successful_payment
    if payment is None:
        return

    payload = payment.invoice_payload
    if not payload or not payload.isdigit():
        logger.error("successful_payment with invalid payload: %s", payload)
        return

    order_id = int(payload)
    telegram_charge_id = payment.telegram_payment_charge_id or ""
    provider_charge_id = payment.provider_payment_charge_id or ""

    checkout = CheckoutService(session_factory)

    try:
        await checkout.confirm_payment(
            order_id,
            telegram_charge_id=telegram_charge_id,
            provider_charge_id=provider_charge_id,
        )
    except NotFoundError:
        logger.error("successful_payment: order %d not found", order_id)
        await message.answer("❌ Pesanan tidak ditemukan. Hubungi support.")
        return
    except Exception as exc:
        logger.error("confirm_payment failed for order %d: %s", order_id, exc)
        await message.answer(fmt_payment_failed("Kesalahan internal. Hubungi support."))
        return

    # Clear the FSM state if the user was in checkout
    try:
        await state.clear()
    except Exception:
        pass  # state may not be active

    # Load order for the receipt message
    async with UnitOfWork(session_factory) as uow:
        order = await uow.orders.get(order_id)

    if order is not None:
        text = fmt_payment_success(order.id, order.total_smallest_unit, settings.CURRENCY)
    else:
        text = fmt_payment_success(order_id, 0, settings.CURRENCY)

    await message.answer(text)

    # ── Low-stock admin notification (Phase 6) ─────────────
    try:
        await _notify_low_stock(message.bot, session_factory)
    except Exception as exc:
        logger.error("low_stock_notify error after payment: %s", exc)


# ── Off-platform payment webhook handler (future) ──────────
#
# When running in webhook mode, this endpoint receives payment
# confirmations from Pakasir or other off-platform providers.
# The route is registered on the aiohttp/FastAPI app, not via aiogram.
#
# async def pakasir_webhook(request):
#     ...
