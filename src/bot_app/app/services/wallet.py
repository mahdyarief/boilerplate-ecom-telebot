"""Wallet service — business logic for saldo (wallet) operations.

All wallet mutations run within a UnitOfWork transaction to ensure
atomicity.  Debit operations use ``WHERE balance >= amount`` guards
at the SQL level to prevent balance from going negative even under
concurrent access.
"""

from __future__ import annotations

import logging

from ...core.constants import PaymentStatus, WalletTransactionType
from ...core.errors import WalletError
from ...infrastructure.persistence.uow import UnitOfWork

logger = logging.getLogger(__name__)


class WalletService:
    """Orchestrates wallet operations: top-up, pay, refund, admin adjust."""

    def __init__(self, session_factory) -> None:  # type: ignore[valid-type]
        self._session_factory = session_factory

    # ── Balance query ────────────────────────────────────

    async def get_balance(self, user_id: int) -> int:
        """Return the user's wallet balance in smallest currency unit.

        Creates the wallet on first access (balance = 0).
        """
        async with UnitOfWork(self._session_factory) as uow:
            wallet = await uow.wallets.get_or_create(user_id)
            return wallet.balance_smallest_unit

    # ── Top-up (admin) ──────────────────────────────────

    async def top_up(
        self,
        user_id: int,
        amount: int,
        *,
        note: str | None = None,
    ) -> int:
        """Credit *amount* to the user's wallet (admin action).

        Returns the new balance after the top-up.
        """
        if amount <= 0:
            raise WalletError("Jumlah top-up harus lebih dari 0.")

        async with UnitOfWork(self._session_factory) as uow:
            wallet = await uow.wallets.get_or_create(user_id)
            tx = await uow.wallets.credit(
                wallet.id,
                amount,
                transaction_type=WalletTransactionType.TOP_UP.value,
                note=note or "Top-up saldo",
            )
            logger.info(
                "wallet top_up: user=%d amount=%d balance_after=%d",
                user_id, amount, tx.balance_after,
            )
            return tx.balance_after

    # ── Pay from wallet ──────────────────────────────────

    async def pay_order(
        self,
        user_id: int,
        order_id: int,
        amount: int,
    ) -> int:
        """Debit *amount* from the user's wallet to pay for an order.

        This operation is atomic: if the balance is insufficient the
        entire transaction is rolled back and a :class:`WalletError` is
        raised.

        Returns the new balance after the payment.
        """
        if amount <= 0:
            raise WalletError("Jumlah pembayaran harus lebih dari 0.")

        async with UnitOfWork(self._session_factory) as uow:
            wallet = await uow.wallets.get_or_create(user_id)

            if wallet.balance_smallest_unit < amount:
                raise WalletError(
                    f"Saldo tidak cukup. Saldo Anda: {wallet.balance_smallest_unit}, "
                    f"dibutuhkan: {amount}."
                )

            try:
                tx = await uow.wallets.debit(
                    wallet.id,
                    amount,
                    transaction_type=WalletTransactionType.PAYMENT.value,
                    order_id=order_id,
                    note=f"Pembayaran pesanan #{order_id}",
                )
            except ValueError:
                raise WalletError("Saldo tidak cukup.")

            logger.info(
                "wallet payment: user=%d order=%d amount=%d balance_after=%d",
                user_id, order_id, amount, tx.balance_after,
            )
            return tx.balance_after

    # ── Refund to wallet ─────────────────────────────────

    async def refund_order(
        self,
        user_id: int,
        order_id: int,
        amount: int,
        *,
        note: str | None = None,
    ) -> int:
        """Credit *amount* back to the user's wallet (refund).

        Returns the new balance after the refund.
        """
        if amount <= 0:
            raise WalletError("Jumlah refund harus lebih dari 0.")

        async with UnitOfWork(self._session_factory) as uow:
            wallet = await uow.wallets.get_or_create(user_id)
            tx = await uow.wallets.credit(
                wallet.id,
                amount,
                transaction_type=WalletTransactionType.REFUND.value,
                order_id=order_id,
                note=note or f"Refund pesanan #{order_id}",
            )
            logger.info(
                "wallet refund: user=%d order=%d amount=%d balance_after=%d",
                user_id, order_id, amount, tx.balance_after,
            )
            return tx.balance_after

    # ── Admin adjust ─────────────────────────────────────

    async def admin_adjust(
        self,
        user_id: int,
        amount: int,
        *,
        note: str | None = None,
    ) -> int:
        """Directly adjust a user's wallet balance (admin action).

        Use positive *amount* to credit and negative to debit.
        Debit operations are guarded against insufficient balance.

        Returns the new balance after the adjustment.
        """
        if amount == 0:
            raise WalletError("Jumlah penyesuaian tidak boleh 0.")

        async with UnitOfWork(self._session_factory) as uow:
            wallet = await uow.wallets.get_or_create(user_id)

            if amount > 0:
                tx = await uow.wallets.credit(
                    wallet.id,
                    abs(amount),
                    transaction_type=WalletTransactionType.ADMIN_ADJUST.value,
                    note=note or "Penyesuaian saldo oleh admin",
                )
            else:
                try:
                    tx = await uow.wallets.debit(
                        wallet.id,
                        abs(amount),
                        transaction_type=WalletTransactionType.ADMIN_ADJUST.value,
                        note=note or "Penyesuaian saldo oleh admin",
                    )
                except ValueError:
                    raise WalletError("Saldo tidak cukup untuk penyesuaian negatif.")

            logger.info(
                "wallet admin_adjust: user=%d amount=%d balance_after=%d",
                user_id, amount, tx.balance_after,
            )
            return tx.balance_after

    # ── Get transaction history ─────────────────────────

    async def get_transactions(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 10,
    ) -> list:
        """Return the user's recent wallet transactions."""
        async with UnitOfWork(self._session_factory) as uow:
            wallet = await uow.wallets.get_or_create(user_id)
            return list(await uow.wallets.list_transactions(
                wallet.id, offset=offset, limit=limit,
            ))
