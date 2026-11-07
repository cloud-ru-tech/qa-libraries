import logging
from dataclasses import dataclass
from typing import Final

logger = logging.getLogger("shop.client")


@dataclass(frozen=True)
class Product:
    """Товар в каталоге магазина."""

    sku: str
    title: str
    price: int


CATALOG: Final[dict[str, Product]] = {
    "SKU-COFFEE": Product("SKU-COFFEE", "Кофе в зёрнах, 1 кг", 600),
    "SKU-TEA": Product("SKU-TEA", "Чай листовой, 200 г", 350),
    "SKU-CUP": Product("SKU-CUP", "Кружка керамическая", 450),
}

EXPIRED_PROMO_CODES: Final[frozenset[str]] = frozenset({"SALE10"})

_DISCOUNT: Final = 0.9


class ShopClient:
    """Заглушка вместо настоящего API-клиента: по сети ничего не ходит, только пишет логи."""

    def __init__(self, base_url: str) -> None:
        """Инициализировать объект.

        :param base_url: значение настройки ``base_url``.
        """
        self._base_url = base_url
        self._items: dict[str, int] = {}
        logger.debug("клиент создан, base_url=%s", base_url)

    def product(self, sku: str) -> Product:
        """Возвращает товар по артикулу."""
        logger.debug("GET %s/catalog/%s", self._base_url, sku)
        product = CATALOG.get(sku)
        if product is None:
            logger.warning("товара %s нет в каталоге", sku)
            message = f"нет такого товара: {sku}"
            raise LookupError(message)
        logger.info("товар %s — %s, цена %s", sku, product.title, product.price)
        return product

    def add_to_cart(self, sku: str, quantity: int) -> None:
        """Добавляет товар в корзину."""
        product = self.product(sku)
        self._items[sku] = self._items.get(sku, 0) + quantity
        logger.info("в корзину добавлено %s × %s", quantity, product.title)

    def clear_cart(self) -> None:
        """Очищает корзину."""
        logger.info("очищаем корзину, позиций было: %s", len(self._items))
        self._items.clear()

    def total(self) -> int:
        """Считает сумму корзины."""
        total = sum(CATALOG[sku].price * quantity for sku, quantity in self._items.items())
        logger.info("сумма корзины: %s", total)
        return total

    def apply_promo(self, code: str) -> int:
        """Считает сумму корзины с учётом промокода."""
        logger.info("применяем промокод %s", code)
        if code in EXPIRED_PROMO_CODES:
            logger.warning("промокод %s просрочен, скидки не будет", code)
            return self.total()
        discounted = round(self.total() * _DISCOUNT)
        logger.info("промокод %s принят, к оплате %s", code, discounted)
        return discounted

    def pay(self, amount: int) -> str:
        """Оплачивает заказ и возвращает его номер."""
        order_id = f"ORD-{amount}"
        logger.info("POST %s/payments amount=%s, создан заказ %s", self._base_url, amount, order_id)
        return order_id
