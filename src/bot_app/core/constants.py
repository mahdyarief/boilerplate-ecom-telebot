"""Shared constants and enumerations (Phase 0 stubs)."""

from __future__ import annotations

from enum import Enum


class CommandName(str, Enum):
    """Bot command names — SSOT for command strings."""

    START = "/start"
    HELP = "/help"
    PING = "/ping"
    ECHO = "/echo"
    CATALOG = "/catalog"
    CART = "/cart"
    ORDERS = "/orders"
    ADMIN = "/admin"


class OrderStatus(str, Enum):
    PENDING = "pending"
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"
