"""Wallet FSM states — aiogram StatesGroup for admin wallet operations.

State machine::

    WalletTopUp
    ┌─────────────────────────────┐
    │ (none)                      │
    └──────────┬──────────────────┘
               │ adm:wl_topup
               ▼
    ┌─────────────────────────────┐
    │ WalletTopUp.user_id          │ ◄── admin types target user ID
    └──────────┬──────────────────┘
               │ message received
               ▼
    ┌─────────────────────────────┐
    │ WalletTopUp.amount           │ ◄── admin types amount
    └──────────┬──────────────────┘
               │ message received
               ▼
    ┌─────────────────────────────┐
    │ WalletTopUp.note             │ ◄── admin types note (or /skip)
    └──────────┬──────────────────┘
               │ message received
               ▼
    │ (none) — top-up executed    │

    WalletAdjust
    ┌─────────────────────────────┐
    │ (none)                      │
    └──────────┬──────────────────┘
               │ adm:wl_adj
               ▼
    ┌─────────────────────────────┐
    │ WalletAdjust.user_id         │ ◄── admin types target user ID
    └──────────┬──────────────────┘
               │ message received
               ▼
    ┌─────────────────────────────┐
    │ WalletAdjust.amount          │ ◄── admin types amount (+/-)
    └──────────┬──────────────────┘
               │ message received
               ▼
    ┌─────────────────────────────┐
    │ WalletAdjust.note            │ ◄── admin types note (or /skip)
    └──────────┬──────────────────┘
               │ message received
               ▼
    │ (none) — adjustment done    │
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class WalletTopUp(StatesGroup):
    """FSM states for admin wallet top-up."""

    user_id = State()
    amount = State()
    note = State()


class WalletAdjust(StatesGroup):
    """FSM states for admin wallet adjustment."""

    user_id = State()
    amount = State()
    note = State()
