"""/start and /help command handlers."""

from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

from ...core.config import settings

router = Router(name="start")


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    """Welcome message shown on /start."""
    text = (
        f"🛍️ Selamat datang di {settings.SHOP_NAME}!\n\n"
        "Jelajahi katalog, tambahkan produk ke keranjang, "
        "dan lakukan pembayaran — semua di dalam Telegram.\n\n"
        "/catalog — Lihat produk\n"
        "/cart — Keranjang Anda\n"
        "/wallet — Cek saldo\n"
        "/orders — Riwayat pesanan\n"
        "/help — Tampilkan bantuan"
    )
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    """Dynamic help listing all commands."""
    lines = [
        "📖 Perintah yang tersedia:\n",
        "/start — Sambutan & pengenalan",
        "/help — Pesan ini",
        "/ping — Cek apakah bot hidup",
        "/echo <teks> — Mengulang teks",
        "/catalog — Lihat katalog produk",
        "/cart — Lihat keranjang",
        "/wallet — Cek saldo",
        "/orders — Riwayat pesanan Anda",
    ]
    if settings.admin_ids:
        lines.append("/admin — Panel admin")
    await message.answer("\n".join(lines))
