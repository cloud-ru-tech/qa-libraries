import logging

import pytest
from assertpy import assert_that

from examples.logging.shop import ShopClient

logger = logging.getLogger("tests")


def test_cart_holds_single_product(shop: ShopClient) -> None:
    logger.info("кладём в корзину один товар")
    shop.add_to_cart("SKU-TEA", 1)
    assert_that(shop.total()).is_equal_to(350)


@pytest.mark.parametrize(
    ("sku", "quantity", "expected_total"),
    [("SKU-COFFEE", 2, 1200), ("SKU-CUP", 3, 1350)],
)
def test_cart_sums_up_quantity(sku: str, quantity: int, expected_total: int, shop: ShopClient) -> None:
    logger.info("кладём в корзину %s штук товара %s", quantity, sku)
    shop.add_to_cart(sku, quantity)
    assert_that(shop.total()).is_equal_to(expected_total)


def test_cart_becomes_empty_after_clear(shop: ShopClient) -> None:
    logger.info("наполняем корзину и сразу очищаем её")
    shop.add_to_cart("SKU-TEA", 2)
    shop.clear_cart()
    assert_that(shop.total()).is_equal_to(0)
