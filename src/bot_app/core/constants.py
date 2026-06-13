"""Shared constants and enumerations (Phase 0 stubs)."""

from __future__ import annotations

from enum import StrEnum


class CommandName(StrEnum):
    """Bot command names — SSOT for command strings."""

    START = "/start"
    HELP = "/help"
    PING = "/ping"
    ECHO = "/echo"
    CATALOG = "/catalog"
    CART = "/cart"
    ORDERS = "/orders"
    ADMIN = "/admin"
    WALLET = "/wallet"
    SALDO = "/saldo"


class OrderStatus(StrEnum):
    PENDING = "pending"
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


class CouponStatus(StrEnum):
    ACTIVE = "active"
    EXHAUSTED = "exhausted"
    EXPIRED = "expired"
    DISABLED = "disabled"


class WalletTransactionType(StrEnum):
    """Types of wallet transactions."""
    TOP_UP = "top_up"
    PAYMENT = "payment"
    REFUND = "refund"
    ADMIN_ADJUST = "admin_adjust"
