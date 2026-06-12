"""Tests for keyboard builder helpers."""

from __future__ import annotations

from types import SimpleNamespace

from bot_app.shared.keyboards import (
    PREFIX_BACK_CATALOG,
    PREFIX_BACK_ROOT,
    PREFIX_CART_ADD,
    PREFIX_CART_CLEAR,
    PREFIX_CART_QTY,
    PREFIX_CART_REMOVE,
    PREFIX_CATEGORY,
    PREFIX_CHECKOUT,
    PREFIX_ORDER,
    PREFIX_ORDER_CANCEL,
    PREFIX_ORDERS_BACK,
    PREFIX_PRODUCT,
    cart_footer_kb,
    cart_item_kb,
    categories_kb,
    checkout_confirm_kb,
    confirm_clear_kb,
    order_detail_kb,
    orders_list_kb,
    product_detail_kb,
    subcategories_or_products_kb,
)


def _make_category(id_: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=id_, name=name)


def _make_subcategory(id_: int, name: str, parent_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=id_, name=name, parent_id=parent_id)


# ── categories_kb ──────────────────────────────────────────────


class TestCategoriesKb:
    def test_empty(self) -> None:
        kb = categories_kb([])
        assert kb.inline_keyboard == []

    def test_single_category(self) -> None:
        cat = _make_category(1, "Electronics")
        kb = categories_kb([cat])
        assert len(kb.inline_keyboard) == 1
        btn = kb.inline_keyboard[0][0]
        assert btn.text == "Electronics"
        assert btn.callback_data == f"{PREFIX_CATEGORY}1"

    def test_multiple_categories(self) -> None:
        cats = [_make_category(i, f"Cat{i}") for i in range(1, 4)]
        kb = categories_kb(cats)
        assert len(kb.inline_keyboard) == 3
        for i, row in enumerate(kb.inline_keyboard, start=1):
            assert row[0].callback_data == f"{PREFIX_CATEGORY}{i}"


# ── subcategories_or_products_kb ────────────────────────────────


class TestSubcategoriesOrProductsKb:
    def test_with_subcategories_and_back(self) -> None:
        sc1 = _make_subcategory(2, "Phones", parent_id=1)
        sc2 = _make_subcategory(3, "Laptops", parent_id=1)
        kb = subcategories_or_products_kb(parent_id=1, subcategories=[sc1, sc2])
        assert len(kb.inline_keyboard) == 3  # 2 subcategories + 1 back button
        # Back button callback
        back_btn = kb.inline_keyboard[-1][0]
        assert back_btn.callback_data == f"{PREFIX_BACK_CATALOG}:1"

    def test_no_subcategories(self) -> None:
        kb = subcategories_or_products_kb(parent_id=5, subcategories=[])
        assert len(kb.inline_keyboard) == 1  # only back button


# ── product_detail_kb ──────────────────────────────────────────


class TestProductDetailKb:
    def test_full_keyboard(self) -> None:
        kb = product_detail_kb(product_id=10, category_id=3)
        assert len(kb.inline_keyboard) == 3

        # Add to cart
        add_btn = kb.inline_keyboard[0][0]
        assert add_btn.callback_data == f"{PREFIX_CART_ADD}10"

        # Back to category
        back_btn = kb.inline_keyboard[1][0]
        assert back_btn.callback_data == f"{PREFIX_BACK_CATALOG}:3"

        # Root
        root_btn = kb.inline_keyboard[2][0]
        assert root_btn.callback_data == PREFIX_BACK_ROOT


# ── cart_item_kb ────────────────────────────────────────────────


class TestCartItemKb:
    def test_buttons(self) -> None:
        kb = cart_item_kb(cart_item_id=5, quantity=3)
        assert len(kb.inline_keyboard) == 2  # +/- row + remove row

        minus, qty_display, plus = kb.inline_keyboard[0]
        assert minus.callback_data == f"{PREFIX_CART_QTY}5:-"
        assert qty_display.text == "3"
        assert plus.callback_data == f"{PREFIX_CART_QTY}5:+"

        remove = kb.inline_keyboard[1][0]
        assert remove.callback_data == f"{PREFIX_CART_REMOVE}5"

    def test_quantity_1(self) -> None:
        kb = cart_item_kb(cart_item_id=1, quantity=1)
        qty_display = kb.inline_keyboard[0][1]
        assert qty_display.text == "1"


# ── cart_footer_kb ──────────────────────────────────────────────


class TestCartFooterKb:
    def test_buttons(self) -> None:
        kb = cart_footer_kb()
        assert len(kb.inline_keyboard) == 3  # checkout + catalog + clear
        checkout_btn = kb.inline_keyboard[0][0]
        assert checkout_btn.callback_data == f"{PREFIX_CHECKOUT}start"
        catalog_btn = kb.inline_keyboard[1][0]
        assert catalog_btn.callback_data == PREFIX_BACK_ROOT
        clear_btn = kb.inline_keyboard[2][0]
        assert clear_btn.callback_data == PREFIX_CART_CLEAR


# ── confirm_clear_kb ────────────────────────────────────────────


class TestConfirmClearKb:
    def test_yes_no(self) -> None:
        kb = confirm_clear_kb()
        assert len(kb.inline_keyboard) == 2
        yes_btn = kb.inline_keyboard[0][0]
        no_btn = kb.inline_keyboard[1][0]
        assert yes_btn.callback_data == f"{PREFIX_CART_CLEAR}yes"
        assert no_btn.callback_data == f"{PREFIX_CART_CLEAR}no"


# ── checkout_confirm_kb ────────────────────────────────────────


class TestCheckoutConfirmKb:
    def test_confirm_cancel(self) -> None:
        kb = checkout_confirm_kb()
        assert len(kb.inline_keyboard) == 2
        confirm_btn = kb.inline_keyboard[0][0]
        cancel_btn = kb.inline_keyboard[1][0]
        assert confirm_btn.callback_data == f"{PREFIX_CHECKOUT}confirm"
        assert cancel_btn.callback_data == f"{PREFIX_CHECKOUT}cancel"


# ── orders_list_kb ────────────────────────────────────────────


class TestOrdersListKb:
    def test_empty(self) -> None:
        kb = orders_list_kb([])
        assert kb.inline_keyboard == []

    def test_with_orders(self) -> None:
        orders = [
            SimpleNamespace(id=1, total_smallest_unit=50000, status="paid"),
        ]
        kb = orders_list_kb(orders)
        assert len(kb.inline_keyboard) == 1
        btn = kb.inline_keyboard[0][0]
        assert btn.callback_data == f"{PREFIX_ORDER}1"

    def test_max_10_orders(self) -> None:
        orders = [SimpleNamespace(id=i, total_smallest_unit=10000, status="paid") for i in range(15)]
        kb = orders_list_kb(orders)
        assert len(kb.inline_keyboard) == 10


# ── order_detail_kb ───────────────────────────────────────────


class TestOrderDetailKb:
    def test_cancellable(self) -> None:
        kb = order_detail_kb(1, cancellable=True)
        # Cancel button + back button
        assert len(kb.inline_keyboard) == 2
        cancel_btn = kb.inline_keyboard[0][0]
        back_btn = kb.inline_keyboard[1][0]
        assert cancel_btn.callback_data == f"{PREFIX_ORDER_CANCEL}1"
        assert back_btn.callback_data == PREFIX_ORDERS_BACK

    def test_not_cancellable(self) -> None:
        kb = order_detail_kb(1, cancellable=False)
        assert len(kb.inline_keyboard) == 1
        back_btn = kb.inline_keyboard[0][0]
        assert back_btn.callback_data == PREFIX_ORDERS_BACK
