"""Admin FSM states — aiogram StatesGroup for admin create/edit flows.

State machine::

    CategoryCreate
    ┌─────────────────────────────┐
    │ (none)                      │
    └──────────┬──────────────────┘
               │ adm:cat_new
               ▼
    ┌─────────────────────────────┐
    │ CategoryCreate.name          │ ◄── user types category name
    └──────────┬──────────────────┘
               │ message received
               ▼
    ┌─────────────────────────────┐
    │ CategoryCreate.slug          │ ◄── user types slug
    └──────────┬──────────────────┘
               │ message received
               ▼
    │ (none) — category created   │

    CategoryEdit
    ┌─────────────────────────────┐
    │ (none)                      │
    └──────────┬──────────────────┘
               │ adm:cat_edit:<id>
               ▼
    ┌─────────────────────────────┐
    │ CategoryEdit.field           │ ◄── user picks which field to edit
    └──────────┬──────────────────┘
               │ callback received
               ▼
    ┌─────────────────────────────┐
    │ CategoryEdit.value           │ ◄── user types new value
    └──────────┬──────────────────┘
               │ message received
               ▼
    │ (none) — category updated   │

    ProductCreate
    ┌─────────────────────────────┐
    │ (none)                      │
    └──────────┬──────────────────┘
               │ adm:prd_new
               ▼
    ┌─────────────────────────────┐
    │ ProductCreate.category       │ ◄── user selects category
    └──────────┬──────────────────┘
               │ callback received
               ▼
    ┌─────────────────────────────┐
    │ ProductCreate.name           │ ◄── user types product name
    └──────────┬──────────────────┘
               │ message received
               ▼
    ┌─────────────────────────────┐
    │ ProductCreate.price          │ ◄── user types price
    └──────────┬──────────────────┘
               │ message received
               ▼
    ┌─────────────────────────────┐
    │ ProductCreate.stock          │ ◄── user types stock
    └──────────┬──────────────────┘
               │ message received
               ▼
    ┌─────────────────────────────┐
    │ ProductCreate.description    │ ◄── user types description (or /skip)
    └──────────┬──────────────────┘
               │ message received
               ▼
    │ (none) — product created    │

    ProductEdit
    ┌─────────────────────────────┐
    │ (none)                      │
    └──────────┬──────────────────┘
               │ adm:prd_edit:<id>
               ▼
    ┌─────────────────────────────┐
    │ ProductEdit.field            │ ◄── user picks which field to edit
    └──────────┬──────────────────┘
               │ callback received
               ▼
    ┌─────────────────────────────┐
    │ ProductEdit.value            │ ◄── user types new value
    └──────────┬──────────────────┘
               │ message received
               ▼
    │ (none) — product updated    │

    Broadcast
    ┌─────────────────────────────┐
    │ (none)                      │
    └──────────┬──────────────────┘
               │ adm:bcast
               ▼
    ┌─────────────────────────────┐
    │ Broadcast.message            │ ◄── user types/forwards the message
    └──────────┬──────────────────┘
               │ message received
               ▼
    ┌─────────────────────────────┐
    │ Broadcast.confirm            │ ◄── confirm or cancel broadcast
    └──────────┬──────────────────┘
               │ callback received
               ▼
    │ (none) — broadcast sent     │
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class CategoryCreate(StatesGroup):
    """FSM states for creating a new category."""

    name = State()
    slug = State()


class CategoryEdit(StatesGroup):
    """FSM states for editing an existing category."""

    field = State()
    value = State()


class ProductCreate(StatesGroup):
    """FSM states for creating a new product."""

    category = State()
    name = State()
    price = State()
    stock = State()
    description = State()


class ProductEdit(StatesGroup):
    """FSM states for editing an existing product."""

    field = State()
    value = State()


class Broadcast(StatesGroup):
    """FSM states for broadcasting a message to all users."""

    message = State()
    confirm = State()


class CouponCreate(StatesGroup):
    """FSM states for creating a new coupon."""

    code = State()
    discount_percent = State()
    max_uses = State()
    expires_at = State()


class ProductImageUpload(StatesGroup):
    """FSM states for uploading a product image."""

    photo = State()
