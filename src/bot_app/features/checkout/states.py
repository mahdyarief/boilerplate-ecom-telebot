"""Checkout FSM states — aiogram StatesGroup for the checkout flow.

State machine::

    ┌──────────────────────┐
    │ (none)               │
    └──────────┬───────────┘
               │ /checkout or cko:start
               ▼
    ┌──────────────────────┐
    │ CheckoutStates.address│ ◄── user types their shipping address
    └──────────┬───────────┘
               │ message received
               ▼
    ┌──────────────────────┐
    │ CheckoutStates.review │ ◄── order summary, confirm / cancel
    └──────────┬───────────┘
               │ cko:confirm
               ▼
    ┌──────────────────────┐
    │ CheckoutStates.paying │ ◄── invoice sent, awaiting payment
    └──────────┬───────────┘
               │ successful_payment / timeout
               ▼
    │ (none)               │
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class CheckoutStates(StatesGroup):
    """FSM states for the checkout flow."""

    address = State()
    review = State()
    coupon_code = State()
    paying = State()
