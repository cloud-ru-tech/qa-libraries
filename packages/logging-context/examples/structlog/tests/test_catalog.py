import pytest
import structlog
from assertpy import assert_that

from examples.structlog.shop import CATALOG, ShopClient

logger = structlog.stdlib.get_logger("tests")


@pytest.mark.parametrize("sku", sorted(CATALOG))
def test_catalog_returns_product_by_sku(sku: str, shop: ShopClient) -> None:
    logger.info("запрашиваем товар", sku=sku)
    assert_that(shop.product(sku).sku).is_equal_to(sku)


@pytest.mark.parametrize(
    ("sku", "expected_price"),
    [("SKU-COFFEE", 600), ("SKU-TEA", 350), ("SKU-CUP", 450)],
)
def test_catalog_keeps_price(sku: str, expected_price: int, shop: ShopClient) -> None:
    logger.info("проверяем цену товара", sku=sku, expected_price=expected_price)
    assert_that(shop.product(sku).price).is_equal_to(expected_price)


def test_catalog_rejects_unknown_sku(shop: ShopClient) -> None:
    logger.info("запрашиваем товар, которого нет в каталоге")
    with pytest.raises(LookupError, match="SKU-MISSING"):
        shop.product("SKU-MISSING")
