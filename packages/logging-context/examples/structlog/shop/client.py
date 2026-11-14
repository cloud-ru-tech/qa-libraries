from dataclasses import dataclass
from typing import Final

import structlog

logger = structlog.stdlib.get_logger("shop.client")


@dataclass(frozen=True)
class Product:
    """Product in the shop catalog."""

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
    """Fake API client that only logs and makes no network calls."""

    def __init__(self, base_url: str) -> None:
        """Initialize the object.

        :param base_url: ``base_url`` setting value.
        """
        self._base_url = base_url
        self._items: dict[str, int] = {}
        self._log = logger.bind(base_url=base_url)
        self._log.debug("клиент создан")

    def product(self, sku: str) -> Product:
        """Return a product by its SKU."""
        self._log.debug("запрос каталога", method="GET", path="/catalog", sku=sku)
        product = CATALOG.get(sku)
        if product is None:
            self._log.warning("товара нет в каталоге", sku=sku)
            message = f"нет такого товара: {sku}"
            raise LookupError(message)
        self._log.info("товар найден", sku=sku, title=product.title, price=product.price)
        return product

    def add_to_cart(self, sku: str, quantity: int) -> None:
        """Add a product to the cart."""
        product = self.product(sku)
        self._items[sku] = self._items.get(sku, 0) + quantity
        self._log.info("товар добавлен в корзину", sku=sku, title=product.title, quantity=quantity)

    def clear_cart(self) -> None:
        """Clear the cart."""
        self._log.info("корзина очищена", items=len(self._items))
        self._items.clear()

    def total(self) -> int:
        """Calculate the cart total."""
        total = sum(CATALOG[sku].price * quantity for sku, quantity in self._items.items())
        self._log.info("сумма корзины посчитана", total=total, items=len(self._items))
        return total

    def apply_promo(self, code: str) -> int:
        """Calculate the cart total with a promo code."""
        if code in EXPIRED_PROMO_CODES:
            self._log.warning("промокод просрочен, скидки не будет", promo_code=code)
            return self.total()
        discounted = round(self.total() * _DISCOUNT)
        self._log.info("промокод принят", promo_code=code, total=discounted)
        return discounted

    def pay(self, amount: int) -> str:
        """Pay for the order and return its number."""
        order_id = f"ORD-{amount}"
        self._log.info("заказ оплачен", method="POST", path="/payments", amount=amount, order_id=order_id)
        return order_id
