"""Tests for admin text builder helpers."""

from __future__ import annotations

from types import SimpleNamespace

from bot_app.core.constants import OrderStatus
from bot_app.features.admin.texts import (
    fmt_admin_menu_help,
    fmt_admin_order_detail,
    fmt_admin_order_list,
    fmt_admin_panel,
    fmt_ask_broadcast_message,
    fmt_ask_category_edit_value,
    fmt_ask_category_name,
    fmt_ask_category_slug,
    fmt_ask_product_description,
    fmt_ask_product_edit_value,
    fmt_ask_product_name,
    fmt_ask_product_price,
    fmt_ask_product_stock,
    fmt_ask_select_category,
    fmt_broadcast_cancelled,
    fmt_broadcast_preview,
    fmt_broadcast_sent,
    fmt_category_created,
    fmt_category_detail,
    fmt_category_list,
    fmt_category_updated,
    fmt_not_admin,
    fmt_order_status_updated,
    fmt_product_created,
    fmt_product_detail,
    fmt_product_list,
    fmt_product_updated,
)


# ── Panel and general texts ──────────────────────────────


class TestFmtAdminPanel:
    def test_format(self) -> None:
        text = fmt_admin_panel()
        assert "Panel Admin" in text
        assert "Pilih aksi" in text


class TestFmtAdminMenuHelp:
    def test_format(self) -> None:
        text = fmt_admin_menu_help()
        assert "/admin" in text
        assert "Perintah Admin" in text


class TestFmtNotAdmin:
    def test_format(self) -> None:
        text = fmt_not_admin()
        assert "bukan admin" in text


# ── Category texts ───────────────────────────────────────


def _make_category(id_: int, name: str, slug: str = "", is_active: bool = True,
                   position: int = 0, parent_id: int | None = None,
                   children: list | None = None, products: list | None = None) -> SimpleNamespace:
    if not slug:
        slug = name.lower().replace(" ", "-")
    return SimpleNamespace(
        id=id_, name=name, slug=slug, is_active=is_active,
        position=position, parent_id=parent_id,
        children=children or [],
        products=products or [],
    )


class TestFmtCategoryList:
    def test_empty(self) -> None:
        text = fmt_category_list([])
        assert "belum ada" in text.lower() or "Kategori" in text

    def test_with_categories(self) -> None:
        cats = [
            _make_category(1, "Electronics", is_active=True),
            _make_category(2, "Inactive Cat", is_active=False),
        ]
        text = fmt_category_list(cats, include_inactive=True)
        assert "Electronics" in text
        assert "Inactive Cat" in text
        assert "✅" in text
        assert "❌" in text

    def test_exclude_inactive_children(self) -> None:
        """When include_inactive=False, children are not shown."""
        child = _make_category(3, "Inactive Child", is_active=False)
        parent = _make_category(1, "Active Parent", is_active=True, children=[child])
        text = fmt_category_list([parent], include_inactive=False)
        assert "Active Parent" in text
        # Children are not displayed when include_inactive=False
        assert "Inactive Child" not in text

    def test_show_inactive_children(self) -> None:
        """When include_inactive=True, children are shown."""
        child = _make_category(3, "Inactive Child", is_active=False)
        parent = _make_category(1, "Active Parent", is_active=True, children=[child])
        text = fmt_category_list([parent], include_inactive=True)
        assert "Active Parent" in text
        assert "Inactive Child" in text

    def test_with_children(self) -> None:
        child = _make_category(3, "Phones", is_active=True)
        parent = _make_category(1, "Electronics", is_active=True, children=[child])
        text = fmt_category_list([parent], include_inactive=True)
        assert "Electronics" in text
        assert "Phones" in text


class TestFmtCategoryDetail:
    def test_active_category(self) -> None:
        cat = _make_category(1, "Electronics", slug="electronics", is_active=True, position=2)
        text = fmt_category_detail(cat)
        assert "#1" in text
        assert "Electronics" in text
        assert "Aktif" in text
        assert "electronics" in text
        assert "Posisi: 2" in text

    def test_inactive_category(self) -> None:
        cat = _make_category(2, "Old", is_active=False)
        text = fmt_category_detail(cat)
        assert "Nonaktif" in text

    def test_with_parent(self) -> None:
        cat = _make_category(3, "Phones", parent_id=1)
        text = fmt_category_detail(cat)
        assert "Parent: #1" in text

    def test_with_children(self) -> None:
        child = _make_category(4, "Smartphones", is_active=True)
        cat = _make_category(1, "Phones", children=[child])
        text = fmt_category_detail(cat)
        assert "Sub-kategori" in text
        assert "Smartphones" in text

    def test_with_products(self) -> None:
        product = SimpleNamespace(name="iPhone")
        cat = _make_category(1, "Phones", products=[product])
        text = fmt_category_detail(cat)
        assert "Jumlah produk: 1" in text


class TestFmtCategoryCreated:
    def test_format(self) -> None:
        cat = _make_category(5, "New Cat", slug="new-cat")
        text = fmt_category_created(cat)
        assert "dibuat" in text
        assert "#5" in text
        assert "New Cat" in text


class TestFmtCategoryUpdated:
    def test_format(self) -> None:
        cat = _make_category(3, "Updated")
        text = fmt_category_updated(cat)
        assert "diperbarui" in text


class TestFmtAskCategoryName:
    def test_format(self) -> None:
        text = fmt_ask_category_name()
        assert "nama" in text.lower()


class TestFmtAskCategorySlug:
    def test_format(self) -> None:
        text = fmt_ask_category_slug()
        assert "slug" in text.lower()


class TestFmtAskCategoryEditValue:
    def test_format(self) -> None:
        text = fmt_ask_category_edit_value("name", "Old Name")
        assert "name" in text
        assert "Old Name" in text


# ── Product texts ────────────────────────────────────────


def _make_product(id_: int, name: str, price: int = 50000, stock: int = 10,
                   is_active: bool = True, category_id: int = 1,
                   description: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=id_, name=name, price_smallest_unit=price, stock=stock,
        is_active=is_active, category_id=category_id, description=description,
    )


class TestFmtProductList:
    def test_empty(self) -> None:
        text = fmt_product_list([])
        assert "belum ada" in text.lower() or "Produk" in text

    def test_with_products(self) -> None:
        products = [
            _make_product(1, "Widget", price=50000, stock=10),
            _make_product(2, "Gadget", price=0, stock=0, is_active=False),
        ]
        text = fmt_product_list(products, currency="IDR")
        assert "Widget" in text
        assert "Gadget" in text
        assert "✅" in text
        assert "❌" in text


class TestFmtProductDetail:
    def test_with_description(self) -> None:
        p = _make_product(1, "Widget", description="A great widget")
        text = fmt_product_detail(p, currency="IDR")
        assert "#1" in text
        assert "Widget" in text
        assert "A great widget" in text
        assert "Rp 50.000" in text
        assert "Aktif" in text

    def test_without_description(self) -> None:
        p = _make_product(2, "Gadget", description=None)
        text = fmt_product_detail(p, currency="IDR")
        assert "—" in text

    def test_inactive(self) -> None:
        p = _make_product(3, "Old", is_active=False)
        text = fmt_product_detail(p, currency="IDR")
        assert "Nonaktif" in text


class TestFmtProductCreated:
    def test_format(self) -> None:
        p = _make_product(10, "New Product", price=75000, stock=50)
        text = fmt_product_created(p, currency="IDR")
        assert "dibuat" in text
        assert "#10" in text
        assert "New Product" in text
        assert "50" in text


class TestFmtProductUpdated:
    def test_format(self) -> None:
        p = _make_product(5, "Updated")
        text = fmt_product_updated(p)
        assert "diperbarui" in text


class TestFmtAskProductName:
    def test_format(self) -> None:
        assert "nama" in fmt_ask_product_name().lower()


class TestFmtAskProductPrice:
    def test_format(self) -> None:
        assert "harga" in fmt_ask_product_price().lower()


class TestFmtAskProductStock:
    def test_format(self) -> None:
        assert "stok" in fmt_ask_product_stock().lower()


class TestFmtAskProductDescription:
    def test_format(self) -> None:
        assert "deskripsi" in fmt_ask_product_description().lower()


class TestFmtAskProductEditValue:
    def test_format(self) -> None:
        text = fmt_ask_product_edit_value("price", "Rp 50.000")
        assert "price" in text
        assert "Rp 50.000" in text


class TestFmtAskSelectCategory:
    def test_format(self) -> None:
        assert "kategori" in fmt_ask_select_category().lower()


# ── Order management texts ───────────────────────────────


def _make_order(id_: int, user_id: int = 42, status: str = "paid",
                 total: int = 50000, address: str | None = "Jl. Test") -> SimpleNamespace:
    return SimpleNamespace(
        id=id_, user_id=user_id, status=status,
        total_smallest_unit=total, shipping_address=address,
    )


class TestFmtAdminOrderList:
    def test_empty(self) -> None:
        text = fmt_admin_order_list([])
        assert "belum ada" in text.lower() or "Pesanan" in text

    def test_with_orders(self) -> None:
        orders = [
            _make_order(1, status=OrderStatus.PAID.value, total=50000),
            _make_order(2, status=OrderStatus.CANCELLED.value, total=30000),
        ]
        text = fmt_admin_order_list(orders, currency="IDR")
        assert "#1" in text
        assert "#2" in text


class TestFmtAdminOrderDetail:
    def test_basic(self) -> None:
        order = _make_order(1, status=OrderStatus.PAID.value, total=100000, address="Jl. Test")
        items = [SimpleNamespace(product_name="Widget", quantity=2, unit_price_smallest_unit=50000)]
        text = fmt_admin_order_detail(order, items, currency="IDR")
        assert "#1" in text
        assert "paid" in text
        assert "Widget" in text
        assert "Jl. Test" in text

    def test_no_address(self) -> None:
        order = _make_order(2, status=OrderStatus.PENDING.value, address=None)
        items = []
        text = fmt_admin_order_detail(order, items, currency="IDR")
        assert "—" in text


class TestFmtOrderStatusUpdated:
    def test_format(self) -> None:
        text = fmt_order_status_updated(5, "shipped")
        assert "#5" in text
        assert "shipped" in text


# ── Broadcast texts ──────────────────────────────────────


class TestFmtAskBroadcastMessage:
    def test_format(self) -> None:
        text = fmt_ask_broadcast_message()
        assert "Broadcast" in text


class TestFmtBroadcastPreview:
    def test_format(self) -> None:
        text = fmt_broadcast_preview(recipient_count=100, text="Hello!")
        assert "100" in text
        assert "Hello!" in text
        assert "Konfirmasi" in text


class TestFmtBroadcastSent:
    def test_format(self) -> None:
        text = fmt_broadcast_sent(success=95, failed=5)
        assert "95" in text
        assert "5" in text
        assert "Berhasil" in text or "selesai" in text


class TestFmtBroadcastCancelled:
    def test_format(self) -> None:
        text = fmt_broadcast_cancelled()
        assert "dibatalkan" in text.lower() or "Batal" in text
