"""Wallet / saldo feature — user-facing wallet commands and admin management.

Interaction flow:

User commands:
1. ``/wallet``          → show balance + transaction history
2. ``/saldo``           → alias for /wallet

Admin commands:
1. ``adm:wls``          → admin wallet management panel
2. ``adm:wl:<user_id>`` → view a specific user's wallet
3. ``adm:wl_topup``     → start top-up FSM
4. ``adm:wl_adj``       → start adjust FSM

Callback-data schema (all ≤64 bytes):

* ``adm:wls``                — wallet management panel
* ``adm:wl:<user_id>``      — user wallet detail
* ``adm:wl_topup``          — start top-up FSM
* ``adm:wl_adj``            — start adjust FSM
"""

from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from ...app.services.wallet import WalletService
from ...core.config import settings
from ...core.errors import WalletError
from ...infrastructure.persistence.uow import UnitOfWork
from .states import WalletTopUp, WalletAdjust
from .texts import (
    fmt_admin_wallet_detail,
    fmt_admin_wallet_panel,
    fmt_ask_wallet_adjust_amount,
    fmt_ask_wallet_adjust_note,
    fmt_ask_wallet_topup_amount,
    fmt_ask_wallet_topup_note,
    fmt_ask_wallet_user_id,
    fmt_wallet_balance,
    fmt_wallet_topup_success,
    fmt_wallet_adjust_success,
)

logger = logging.getLogger(__name__)

router = Router(name="wallet")

# ── Callback data prefixes ────────────────────────────────

_ADMIN_WALLET_PREFIX = "adm:wls"
_ADMIN_WALLET_USER_PREFIX = "adm:wl:"
_ADMIN_WALLET_TOPUP = "adm:wl_topup"
_ADMIN_WALLET_ADJUST = "adm:wl_adj"


# ══════════════════════════════════════════════════════════
#  USER COMMANDS
# ══════════════════════════════════════════════════════════


@router.message(Command("wallet"))
async def cmd_wallet(
    message: types.Message,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Show the user's wallet balance and recent transactions."""
    user_id = message.from_user.id

    # Ensure user exists
    async with UnitOfWork(session_factory) as uow:
        await uow.users.get_or_create(user_id)

    wallet_svc = WalletService(session_factory)
    balance = await wallet_svc.get_balance(user_id)
    transactions = await wallet_svc.get_transactions(user_id, limit=10)

    text = fmt_wallet_balance(balance, settings.CURRENCY, transactions)
    await message.answer(text)


@router.message(Command("saldo"))
async def cmd_saldo(
    message: types.Message,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Alias for /wallet."""
    await cmd_wallet(message, session_factory)


# ══════════════════════════════════════════════════════════
#  ADMIN WALLET MANAGEMENT
# ══════════════════════════════════════════════════════════


def _is_admin(user_id: int) -> bool:
    """Return ``True`` if *user_id* is in ``settings.admin_ids``."""
    return user_id in settings.admin_ids


@router.callback_query(lambda c: c.data == _ADMIN_WALLET_PREFIX)
async def cb_admin_wallets(callback: types.CallbackQuery) -> None:
    """Show the admin wallet management panel."""
    if not _is_admin(callback.from_user.id):
        from ...features.admin.texts import fmt_not_admin
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    text = fmt_admin_wallet_panel()

    from ...shared.keyboards import admin_wallet_panel_kb
    kb = admin_wallet_panel_kb()

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# ── Admin: View user wallet ──────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith(_ADMIN_WALLET_USER_PREFIX))
async def cb_admin_wallet_user(
    callback: types.CallbackQuery,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Show a user's wallet detail for admin management."""
    if not _is_admin(callback.from_user.id):
        from ...features.admin.texts import fmt_not_admin
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len(_ADMIN_WALLET_USER_PREFIX):]
    if not payload.lstrip("-").isdigit():
        await callback.answer("❌ User ID tidak valid.", show_alert=True)
        return

    target_user_id = int(payload)
    wallet_svc = WalletService(session_factory)
    balance = await wallet_svc.get_balance(target_user_id)
    transactions = await wallet_svc.get_transactions(target_user_id, limit=10)

    text = fmt_admin_wallet_detail(
        target_user_id, balance, settings.CURRENCY, transactions,
    )

    from ...shared.keyboards import admin_wallet_user_kb
    kb = admin_wallet_user_kb(target_user_id)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# ── Admin: Top-up (FSM) ─────────────────────────────────


@router.callback_query(lambda c: c.data == _ADMIN_WALLET_TOPUP)
async def cb_admin_wallet_topup(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start wallet top-up FSM → ask for user ID."""
    if not _is_admin(callback.from_user.id):
        from ...features.admin.texts import fmt_not_admin
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    await state.set_state(WalletTopUp.user_id)
    await callback.message.answer(fmt_ask_wallet_user_id())
    await callback.answer()


@router.message(StateFilter(WalletTopUp.user_id))
async def process_wallet_topup_user_id(message: types.Message, state: FSMContext) -> None:
    """Receive target user ID → ask for amount."""
    if not message.text:
        await message.answer("⚠️ Ketik user ID sebagai angka.")
        return

    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("⚠️ User ID tidak valid. Ketik angka:")
        return

    user_id = int(text)
    await state.update_data(target_user_id=user_id)
    await state.set_state(WalletTopUp.amount)
    await message.answer(fmt_ask_wallet_topup_amount())


@router.message(StateFilter(WalletTopUp.amount))
async def process_wallet_topup_amount(message: types.Message, state: FSMContext) -> None:
    """Receive top-up amount → ask for note."""
    if not message.text:
        await message.answer("⚠️ Ketik jumlah top-up sebagai angka.")
        return

    try:
        amount = int(message.text.strip().replace(".", "").replace(",", ""))
    except ValueError:
        await message.answer("⚠️ Jumlah tidak valid. Ketik angka saja (contoh: 50000):")
        return

    if amount <= 0:
        await message.answer("⚠️ Jumlah harus lebih dari 0.")
        return

    await state.update_data(topup_amount=amount)
    await state.set_state(WalletTopUp.note)
    await message.answer(fmt_ask_wallet_topup_note())


@router.message(StateFilter(WalletTopUp.note))
async def process_wallet_topup_note(
    message: types.Message,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Receive top-up note → execute top-up."""
    note = message.text.strip() if message.text and message.text.strip() != "/skip" else None

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    amount = data.get("topup_amount", 0)

    if target_user_id is None:
        await state.clear()
        await message.answer("❌ Sesi top-up kadaluarsa. Silakan coba lagi.")
        return

    wallet_svc = WalletService(session_factory)

    try:
        new_balance = await wallet_svc.top_up(target_user_id, amount, note=note)
    except WalletError as exc:
        await state.clear()
        await message.answer(f"❌ {exc}")
        return

    await state.clear()
    await message.answer(fmt_wallet_topup_success(
        target_user_id, amount, new_balance, settings.CURRENCY,
    ))


# ── Admin: Adjust (FSM) ────────────────────────────────


@router.callback_query(lambda c: c.data == _ADMIN_WALLET_ADJUST)
async def cb_admin_wallet_adjust(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start wallet adjust FSM → ask for user ID."""
    if not _is_admin(callback.from_user.id):
        from ...features.admin.texts import fmt_not_admin
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    await state.set_state(WalletAdjust.user_id)
    await callback.message.answer(fmt_ask_wallet_user_id())
    await callback.answer()


@router.message(StateFilter(WalletAdjust.user_id))
async def process_wallet_adjust_user_id(message: types.Message, state: FSMContext) -> None:
    """Receive target user ID → ask for amount."""
    if not message.text:
        await message.answer("⚠️ Ketik user ID sebagai angka.")
        return

    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("⚠️ User ID tidak valid. Ketik angka:")
        return

    user_id = int(text)
    await state.update_data(target_user_id=user_id)
    await state.set_state(WalletAdjust.amount)
    await message.answer(fmt_ask_wallet_adjust_amount())


@router.message(StateFilter(WalletAdjust.amount))
async def process_wallet_adjust_amount(message: types.Message, state: FSMContext) -> None:
    """Receive adjust amount → ask for note."""
    if not message.text:
        await message.answer("⚠️ Ketik jumlah penyesuaian sebagai angka.")
        return

    try:
        amount = int(message.text.strip().replace(".", "").replace(",", ""))
    except ValueError:
        await message.answer("⚠️ Jumlah tidak valid. Ketik angka (positif untuk tambah, negatif untuk kurang):")
        return

    if amount == 0:
        await message.answer("⚠️ Jumlah tidak boleh 0.")
        return

    await state.update_data(adjust_amount=amount)
    await state.set_state(WalletAdjust.note)
    await message.answer(fmt_ask_wallet_adjust_note())


@router.message(StateFilter(WalletAdjust.note))
async def process_wallet_adjust_note(
    message: types.Message,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Receive adjust note → execute adjustment."""
    note = message.text.strip() if message.text and message.text.strip() != "/skip" else None

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    amount = data.get("adjust_amount", 0)

    if target_user_id is None:
        await state.clear()
        await message.answer("❌ Sesi penyesuaian kadaluarsa. Silakan coba lagi.")
        return

    wallet_svc = WalletService(session_factory)

    try:
        new_balance = await wallet_svc.admin_adjust(target_user_id, amount, note=note)
    except WalletError as exc:
        await state.clear()
        await message.answer(f"❌ {exc}")
        return

    await state.clear()
    await message.answer(fmt_wallet_adjust_success(
        target_user_id, amount, new_balance, settings.CURRENCY,
    ))
