"""Message text builders for the wallet / saldo feature — pure formatting, no I/O."""

from __future__ import annotations

from ...core.constants import WalletTransactionType
from ...shared.money import Money


# ── User-facing texts ───────────────────────────────────────


def fmt_wallet_balance(
    balance_smallest_unit: int,
    currency: str,
    transactions: list | None = None,
) -> str:
    """Build wallet balance display text with optional transaction history."""
    balance = Money(balance_smallest_unit, currency)
    text = (
        f"💳 **Saldo Anda**\n\n"
        f"💰 Saldo: **{balance.format()}**\n"
    )

    if transactions:
        text += "\n" + _fmt_transaction_list(transactions, currency)

    text += "\n/payments — Lihat semua riwayat transaksi"
    return text


def _fmt_transaction_list(transactions: list, currency: str) -> str:
    """Format a list of wallet transactions."""
    type_emoji = {
        WalletTransactionType.TOP_UP.value: "⬆️",
        WalletTransactionType.PAYMENT.value: "⬇️",
        WalletTransactionType.REFUND.value: "🔄",
        WalletTransactionType.ADMIN_ADJUST.value: "🔧",
    }

    lines = ["📋 **Riwayat Transaksi:**\n"]
    for tx in transactions[:10]:
        emoji = type_emoji.get(tx.transaction_type, "❓")
        amount = Money(abs(tx.amount_smallest_unit), currency)
        balance_after = Money(tx.balance_after, currency)
        sign = "+" if tx.amount_smallest_unit > 0 else "-"
        note = f" {tx.note}" if tx.note else ""
        lines.append(
            f"  {emoji} {sign}{amount.format()} → sisa: {balance_after.format()}{note}"
        )

    return "\n".join(lines)


# ── Admin texts ─────────────────────────────────────────────


def fmt_admin_wallet_panel() -> str:
    """Build the admin wallet management panel text."""
    return (
        "💳 **Manajemen Saldo**\n\n"
        "Pilih aksi di bawah:"
    )


def fmt_admin_wallet_detail(
    user_id: int,
    balance_smallest_unit: int,
    currency: str,
    transactions: list | None = None,
) -> str:
    """Build the admin wallet detail text for a specific user."""
    balance = Money(balance_smallest_unit, currency)
    text = (
        f"💳 **Saldo User {user_id}**\n\n"
        f"💰 Saldo: **{balance.format()}**\n"
    )

    if transactions:
        text += "\n" + _fmt_transaction_list(transactions, currency)

    return text


def fmt_ask_wallet_user_id() -> str:
    """Ask admin for target user ID."""
    return "📝 Ketik user ID Telegram target:"


def fmt_ask_wallet_topup_amount() -> str:
    """Ask admin for top-up amount."""
    return "📝 Ketik jumlah top-up (angka saja, contoh: 50000):"


def fmt_ask_wallet_topup_note() -> str:
    """Ask admin for top-up note."""
    return "📝 Ketik catatan top-up (atau /skip untuk tanpa catatan):"


def fmt_ask_wallet_adjust_amount() -> str:
    """Ask admin for adjustment amount."""
    return (
        "📝 Ketik jumlah penyesuaian:\n"
        "• Positif untuk menambah saldo (contoh: 50000)\n"
        "• Negatif untuk mengurangi saldo (contoh: -10000)"
    )


def fmt_ask_wallet_adjust_note() -> str:
    """Ask admin for adjustment note."""
    return "📝 Ketik catatan penyesuaian (atau /skip untuk tanpa catatan):"


def fmt_wallet_topup_success(
    target_user_id: int,
    amount: int,
    new_balance: int,
    currency: str,
) -> str:
    """Build the top-up success confirmation."""
    amount_money = Money(amount, currency)
    balance_money = Money(new_balance, currency)
    return (
        f"✅ **Top-up Berhasil!**\n\n"
        f"👤 User: {target_user_id}\n"
        f"💰 Jumlah: +{amount_money.format()}\n"
        f"💰 Saldo sekarang: {balance_money.format()}"
    )


def fmt_wallet_adjust_success(
    target_user_id: int,
    amount: int,
    new_balance: int,
    currency: str,
) -> str:
    """Build the adjustment success confirmation."""
    amount_money = Money(abs(amount), currency)
    balance_money = Money(new_balance, currency)
    sign = "+" if amount > 0 else "-"
    action = "ditambah" if amount > 0 else "dikurangi"
    return (
        f"✅ **Penyesuaian Saldo Berhasil!**\n\n"
        f"👤 User: {target_user_id}\n"
        f"💰 Jumlah: {sign}{amount_money.format()} (saldo {action})\n"
        f"💰 Saldo sekarang: {balance_money.format()}"
    )
