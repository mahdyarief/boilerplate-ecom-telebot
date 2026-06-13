"""Tests for admin keyboard builder helpers."""

from __future__ import annotations

from types import SimpleNamespace

from bot_app.shared.keyboards import (
    PREFIX_ADMIN,
    PREFIX_ADMIN_BACK,
    PREFIX_ADMIN_BCAST,
    PREFIX_ADMIN_BCAST_CANCEL,
    PREFIX_ADMIN_BCAST_CONFIRM,
    PREFIX_ADMIN_CAT,
    PREFIX_ADMIN_CAT_DEL,
    PREFIX_ADMIN_CAT_EDIT,
    PREFIX_ADMIN_CAT_NEW,
    PREFIX_ADMIN_CAT_TOGGLE,
    PREFIX_ADMIN_CATS,
    PREFIX_ADMIN_COUPONS,
    PREFIX_ADMIN_ORD,
    PREFIX_ADMIN_ORD_STATUS,
    PREFIX_ADMIN_ORDS,
    PREFIX_ADMIN_PRD,
    PREFIX_ADMIN_PRD_DEL,
    PREFIX_ADMIN_PRD_EDIT,
    PREFIX_ADMIN_PRD_NEW,
    PREFIX_ADMIN_PRD_NEW_CAT,
    PREFIX_ADMIN_PRD_TOGGLE,
    PREFIX_ADMIN_PRDS,
    admin_back_kb,
    admin_broadcast_confirm_kb,
    admin_category_detail_kb,
    admin_category_edit_field_kb,
    admin_category_list_kb,
    admin_order_detail_kb,
    admin_order_list_kb,
    admin_panel_kb,
    admin_product_detail_kb,
    admin_product_edit_field_kb,
    admin_product_list_kb,
    admin_product_new_category_kb,
)


def _make_category(id_: int, name: str, is_active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(id=id_, name=name, is_active=is_active)


def _make_product(id_: int, name: str, is_active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(id=id_, name=name, is_active=is_active)


def _make_order(id_: int, total_smallest_unit: int = 50000, status: str = "paid") -> SimpleNamespace:
    return SimpleNamespace(id=id_, total_smallest_unit=total_smallest_unit, status=status)


# ── admin_panel_kb ───────────────────────────────────────


class TestAdminPanelKb:
    def test_has_six_buttons(self) -> None:
        kb = admin_panel_kb()
        # 6 sections: categories, products, orders, coupons, wallets, broadcast
        assert len(kb.inline_keyboard) == 6

    def test_button_callbacks(self) -> None:
        kb = admin_panel_kb()
        assert kb.inline_keyboard[0][0].callback_data == PREFIX_ADMIN_CATS
        assert kb.inline_keyboard[1][0].callback_data == PREFIX_ADMIN_PRDS
        assert kb.inline_keyboard[2][0].callback_data == PREFIX_ADMIN_ORDS
        assert kb.inline_keyboard[3][0].callback_data == PREFIX_ADMIN_COUPONS
        assert kb.inline_keyboard[4][0].callback_data == "adm:wls"  # Wallet / Saldo
        assert kb.inline_keyboard[5][0].callback_data == PREFIX_ADMIN_BCAST


# ── admin_category_list_kb ────────────────────────────────


class TestAdminCategoryListKb:
    def test_with_categories(self) -> None:
        cats = [
            _make_category(1, "Electronics", is_active=True),
            _make_category(2, "Old Cat", is_active=False),
        ]
        kb = admin_category_list_kb(cats, include_inactive=True)
        # 2 category buttons + New + Back
        assert len(kb.inline_keyboard) == 4
        assert kb.inline_keyboard[0][0].callback_data == f"{PREFIX_ADMIN_CAT}1"
        assert kb.inline_keyboard[1][0].callback_data == f"{PREFIX_ADMIN_CAT}2"

    def test_new_button(self) -> None:
        kb = admin_category_list_kb([], include_inactive=True)
        # New + Back
        assert len(kb.inline_keyboard) == 2
        new_btn = kb.inline_keyboard[0][0]
        assert new_btn.callback_data == PREFIX_ADMIN_CAT_NEW

    def test_back_button(self) -> None:
        kb = admin_category_list_kb([], include_inactive=True)
        back_btn = kb.inline_keyboard[-1][0]
        assert back_btn.callback_data == PREFIX_ADMIN_BACK

    def test_exclude_inactive(self) -> None:
        cats = [
            _make_category(1, "Active", is_active=True),
            _make_category(2, "Inactive", is_active=False),
        ]
        kb = admin_category_list_kb(cats, include_inactive=False)
        # Only 1 category + New + Back
        assert len(kb.inline_keyboard) == 3
        assert kb.inline_keyboard[0][0].text == "✅ Active"


# ── admin_category_detail_kb ───────────────────────────────


class TestAdminCategoryDetailKb:
    def test_active_category(self) -> None:
        kb = admin_category_detail_kb(5, is_active=True)
        assert len(kb.inline_keyboard) == 4  # Edit, Toggle, Delete, Back
        assert kb.inline_keyboard[0][0].callback_data == f"{PREFIX_ADMIN_CAT_EDIT}5"
        toggle_btn = kb.inline_keyboard[1][0]
        assert toggle_btn.callback_data == f"{PREFIX_ADMIN_CAT_TOGGLE}5"
        assert "Nonaktifkan" in toggle_btn.text
        assert kb.inline_keyboard[2][0].callback_data == f"{PREFIX_ADMIN_CAT_DEL}5"
        assert kb.inline_keyboard[3][0].callback_data == PREFIX_ADMIN_CATS

    def test_inactive_category(self) -> None:
        kb = admin_category_detail_kb(3, is_active=False)
        toggle_btn = kb.inline_keyboard[1][0]
        assert "Aktifkan" in toggle_btn.text


# ── admin_category_edit_field_kb ──────────────────────────


class TestAdminCategoryEditFieldKb:
    def test_fields(self) -> None:
        kb = admin_category_edit_field_kb(7)
        assert len(kb.inline_keyboard) == 4  # name, slug, position, cancel

        name_btn = kb.inline_keyboard[0][0]
        assert name_btn.callback_data == f"{PREFIX_ADMIN_CAT_EDIT}7:name"

        slug_btn = kb.inline_keyboard[1][0]
        assert slug_btn.callback_data == f"{PREFIX_ADMIN_CAT_EDIT}7:slug"

        pos_btn = kb.inline_keyboard[2][0]
        assert pos_btn.callback_data == f"{PREFIX_ADMIN_CAT_EDIT}7:position"

        cancel_btn = kb.inline_keyboard[3][0]
        assert cancel_btn.callback_data == f"{PREFIX_ADMIN_CAT}7"


# ── admin_product_list_kb ─────────────────────────────────


class TestAdminProductListKb:
    def test_with_products(self) -> None:
        products = [
            _make_product(1, "Widget", is_active=True),
            _make_product(2, "Gadget", is_active=False),
        ]
        kb = admin_product_list_kb(products, include_inactive=True)
        # 2 products + New + Back
        assert len(kb.inline_keyboard) == 4
        assert kb.inline_keyboard[0][0].callback_data == f"{PREFIX_ADMIN_PRD}1"
        assert kb.inline_keyboard[1][0].callback_data == f"{PREFIX_ADMIN_PRD}2"

    def test_new_button(self) -> None:
        kb = admin_product_list_kb([], include_inactive=True)
        new_btn = kb.inline_keyboard[0][0]
        assert new_btn.callback_data == PREFIX_ADMIN_PRD_NEW

    def test_exclude_inactive(self) -> None:
        products = [
            _make_product(1, "Active", is_active=True),
            _make_product(2, "Inactive", is_active=False),
        ]
        kb = admin_product_list_kb(products, include_inactive=False)
        # Only active product + New + Back
        assert len(kb.inline_keyboard) == 3


# ── admin_product_detail_kb ───────────────────────────────


class TestAdminProductDetailKb:
    def test_active_product(self) -> None:
        kb = admin_product_detail_kb(10, is_active=True)
        # Rows: Edit, Images, Toggle, Delete, Back
        assert len(kb.inline_keyboard) == 5
        toggle_btn = kb.inline_keyboard[2][0]
        assert "Nonaktifkan" in toggle_btn.text

    def test_inactive_product(self) -> None:
        kb = admin_product_detail_kb(10, is_active=False)
        toggle_btn = kb.inline_keyboard[2][0]
        assert "Aktifkan" in toggle_btn.text


# ── admin_product_edit_field_kb ───────────────────────────


class TestAdminProductEditFieldKb:
    def test_fields(self) -> None:
        kb = admin_product_edit_field_kb(8)
        assert len(kb.inline_keyboard) == 5  # name, desc, price, stock, cancel

        name_btn = kb.inline_keyboard[0][0]
        assert name_btn.callback_data == f"{PREFIX_ADMIN_PRD_EDIT}8:name"

        desc_btn = kb.inline_keyboard[1][0]
        assert desc_btn.callback_data == f"{PREFIX_ADMIN_PRD_EDIT}8:description"

        price_btn = kb.inline_keyboard[2][0]
        assert price_btn.callback_data == f"{PREFIX_ADMIN_PRD_EDIT}8:price"

        stock_btn = kb.inline_keyboard[3][0]
        assert stock_btn.callback_data == f"{PREFIX_ADMIN_PRD_EDIT}8:stock"

        cancel_btn = kb.inline_keyboard[4][0]
        assert cancel_btn.callback_data == f"{PREFIX_ADMIN_PRD}8"


# ── admin_product_new_category_kb ─────────────────────────


class TestAdminProductNewCategoryKb:
    def test_with_categories(self) -> None:
        cats = [
            _make_category(1, "Electronics"),
            _make_category(2, "Clothing", is_active=False),
        ]
        kb = admin_product_new_category_kb(cats)
        # Only active categories + cancel
        assert len(kb.inline_keyboard) == 2
        assert kb.inline_keyboard[0][0].callback_data == f"{PREFIX_ADMIN_PRD_NEW_CAT}1"
        assert kb.inline_keyboard[1][0].callback_data == PREFIX_ADMIN_PRDS

    def test_empty(self) -> None:
        kb = admin_product_new_category_kb([])
        assert len(kb.inline_keyboard) == 1  # just cancel
        assert kb.inline_keyboard[0][0].callback_data == PREFIX_ADMIN_PRDS


# ── admin_order_list_kb ──────────────────────────────────


class TestAdminOrderListKb:
    def test_empty(self) -> None:
        kb = admin_order_list_kb([])
        # Only back button
        assert len(kb.inline_keyboard) == 1
        assert kb.inline_keyboard[0][0].callback_data == PREFIX_ADMIN_BACK

    def test_with_orders(self) -> None:
        orders = [_make_order(1, status="paid")]
        kb = admin_order_list_kb(orders, currency="IDR")
        assert len(kb.inline_keyboard) == 2  # 1 order + back
        assert kb.inline_keyboard[0][0].callback_data == f"{PREFIX_ADMIN_ORD}1"

    def test_max_10_orders(self) -> None:
        orders = [_make_order(i) for i in range(15)]
        kb = admin_order_list_kb(orders, currency="IDR")
        assert len(kb.inline_keyboard) == 11  # 10 orders + back


# ── admin_order_detail_kb ────────────────────────────────


class TestAdminOrderDetailKb:
    def test_pending_order_transitions(self) -> None:
        kb = admin_order_detail_kb(1, status="pending")
        # pending → awaiting_payment, cancelled + back
        callbacks = [row[0].callback_data for row in kb.inline_keyboard]
        assert any("awaiting_payment" in c for c in callbacks)
        assert any("cancelled" in c for c in callbacks)
        assert callbacks[-1] == PREFIX_ADMIN_ORDS

    def test_paid_order_transitions(self) -> None:
        kb = admin_order_detail_kb(1, status="paid")
        callbacks = [row[0].callback_data for row in kb.inline_keyboard]
        assert any("shipped" in c for c in callbacks)

    def test_delivered_no_transitions(self) -> None:
        kb = admin_order_detail_kb(1, status="delivered")
        # Only back button
        assert len(kb.inline_keyboard) == 1
        assert kb.inline_keyboard[0][0].callback_data == PREFIX_ADMIN_ORDS

    def test_status_callback_format(self) -> None:
        kb = admin_order_detail_kb(5, status="shipped")
        # shipped → delivered
        delivered_btn = kb.inline_keyboard[0][0]
        assert delivered_btn.callback_data == f"{PREFIX_ADMIN_ORD_STATUS}5:delivered"


# ── admin_broadcast_confirm_kb ────────────────────────────


class TestAdminBroadcastConfirmKb:
    def test_confirm_cancel(self) -> None:
        kb = admin_broadcast_confirm_kb()
        assert len(kb.inline_keyboard) == 2
        assert kb.inline_keyboard[0][0].callback_data == PREFIX_ADMIN_BCAST_CONFIRM
        assert kb.inline_keyboard[1][0].callback_data == PREFIX_ADMIN_BCAST_CANCEL


# ── admin_back_kb ────────────────────────────────────────


class TestAdminBackKb:
    def test_default_target(self) -> None:
        kb = admin_back_kb()
        assert kb.inline_keyboard[0][0].callback_data == PREFIX_ADMIN_BACK

    def test_custom_target(self) -> None:
        kb = admin_back_kb(target=PREFIX_ADMIN_CATS)
        assert kb.inline_keyboard[0][0].callback_data == PREFIX_ADMIN_CATS


# ── Callback data length check ───────────────────────────


class TestCallbackDataLength:
    """All callback data must be ≤64 bytes (Telegram limit)."""

    def test_all_prefixes_within_limit(self) -> None:
        all_prefixes = [
            PREFIX_ADMIN,
            PREFIX_ADMIN_BACK,
            PREFIX_ADMIN_BCAST,
            PREFIX_ADMIN_BCAST_CANCEL,
            PREFIX_ADMIN_BCAST_CONFIRM,
            PREFIX_ADMIN_CAT,
            PREFIX_ADMIN_CAT_DEL,
            PREFIX_ADMIN_CAT_EDIT,
            PREFIX_ADMIN_CAT_NEW,
            PREFIX_ADMIN_CAT_TOGGLE,
            PREFIX_ADMIN_CATS,
            PREFIX_ADMIN_ORD,
            PREFIX_ADMIN_ORD_STATUS,
            PREFIX_ADMIN_ORDS,
            PREFIX_ADMIN_PRD,
            PREFIX_ADMIN_PRD_DEL,
            PREFIX_ADMIN_PRD_EDIT,
            PREFIX_ADMIN_PRD_NEW,
            PREFIX_ADMIN_PRD_NEW_CAT,
            PREFIX_ADMIN_PRD_TOGGLE,
            PREFIX_ADMIN_PRDS,
        ]
        # These are prefixes; actual callback data will have IDs appended
        for prefix in all_prefixes:
            assert len(prefix) <= 64, f"Prefix too long: {prefix!r} ({len(prefix)} bytes)"

    def test_longest_possible_callback_data(self) -> None:
        """Simulate the longest callback data with max-length IDs."""
        # adm:ord_st:999999:awaiting_payment = 35 chars — well within 64
        longest = f"{PREFIX_ADMIN_ORD_STATUS}999999:awaiting_payment"
        assert len(longest) <= 64, f"Longest callback data too long: {longest!r}"

        # adm:prd_edit:999999:description = 31 chars
        long_edit = f"{PREFIX_ADMIN_PRD_EDIT}999999:description"
        assert len(long_edit) <= 64

        # adm:cat_edit:999999:position = 28 chars
        cat_edit = f"{PREFIX_ADMIN_CAT_EDIT}999999:position"
        assert len(cat_edit) <= 64

        # adm:prd_ncat:999999 = 18 chars
        new_cat = f"{PREFIX_ADMIN_PRD_NEW_CAT}999999"
        assert len(new_cat) <= 64
