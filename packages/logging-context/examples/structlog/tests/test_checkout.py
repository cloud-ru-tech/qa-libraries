from itertools import count
from typing import Final

import pytest
import structlog
from assertpy import assert_that

from examples.structlog.shop import ShopClient

logger = structlog.stdlib.get_logger("tests")

_SUCCESSFUL_ATTEMPT: Final = 3

# Счётчик живёт в модуле, поэтому продолжается между повторными попытками одного прогона.
_attempts = count(1)


@pytest.mark.flaky(reruns=2)
def test_checkout_survives_flaky_payment_gateway(shop: ShopClient) -> None:
    """Первые две попытки падают, третья проходит: у каждой попытки будет свой файл логов."""
    attempt = next(_attempts)
    # bind добавляет attempt ко всем записям ниже — в файле это видно в каждой строке.
    log = logger.bind(attempt=attempt)
    log.info("пробуем оплатить заказ")
    shop.add_to_cart("SKU-CUP", 1)
    if attempt < _SUCCESSFUL_ATTEMPT:
        log.error("платёжный шлюз недоступен", status_code=503)
        pytest.fail(f"платёжный шлюз недоступен, попытка {attempt}")
    assert_that(shop.pay(shop.total())).is_equal_to("ORD-450")


def test_checkout_applies_promo_code(shop: ShopClient) -> None:
    """Падает специально: из логов теста видно, что промокод просрочен и скидки не было."""
    logger.info("оформляем заказ с промокодом", promo_code="SALE10")
    shop.add_to_cart("SKU-COFFEE", 2)
    assert_that(shop.apply_promo("SALE10")).is_equal_to(1080)
