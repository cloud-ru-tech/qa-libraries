import pytest
from assertpy import assert_that
from http_client.client import HttpClient

from .support.clients import SyncClientFactory

# Тексты отказов — часть контракта endpoint(): по ним тест отличает,
# какая именно проверка сработала.
RELATIVE_PATH_ONLY = "только относительный путь"
NO_PARENT_TRAVERSAL = "выход вверх по пути"


class ClientWithTrailingSlash(HttpClient):
    DEFAULT_URL_SUFFIX = "/u-api/orders/v1/"


class ClientWithoutTrailingSlash(HttpClient):
    DEFAULT_URL_SUFFIX = "/u-api/orders/v1"


def test_suffix_with_trailing_slash_is_prepended(new_client: SyncClientFactory) -> None:
    """Суффикс со слешем на конце подставляется целиком."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    url = client.endpoint("orders/123")

    assert_that(url).is_equal_to("/u-api/orders/v1/orders/123")


def test_suffix_without_trailing_slash_keeps_last_segment(new_client: SyncClientFactory) -> None:
    """Суффикс без слеша на конце не теряет последний сегмент.

    Регрессия: urljoin принимал "v1" за имя файла и отбрасывал его,
    из-за чего получалось /u-api/orders/orders/123.
    """
    client = new_client("https://example.com", cls=ClientWithoutTrailingSlash)

    url = client.endpoint("orders/123")

    assert_that(url).is_equal_to("/u-api/orders/v1/orders/123")


def test_leading_slash_in_path_is_stripped(new_client: SyncClientFactory) -> None:
    """Ведущий слеш в пути не влияет на результат."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    url = client.endpoint("/orders/123")

    assert_that(url).is_equal_to("/u-api/orders/v1/orders/123")


def test_empty_path_returns_suffix(new_client: SyncClientFactory) -> None:
    """Пустой путь даёт сам суффикс."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    url = client.endpoint("")

    assert_that(url).is_equal_to("/u-api/orders/v1/")


def test_empty_suffix_returns_path_unchanged(new_client: SyncClientFactory) -> None:
    """Без суффикса возвращается сам путь."""
    client = new_client("https://example.com")

    url = client.endpoint("/orders/123")

    assert_that(url).is_equal_to("orders/123")


def test_absolute_url_is_rejected(new_client: SyncClientFactory) -> None:
    """Абсолютный URL не может подменить базовый адрес клиента."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    with pytest.raises(ValueError, match=RELATIVE_PATH_ONLY):
        client.endpoint("https://evil.example/steal")


def test_protocol_relative_url_is_rejected(new_client: SyncClientFactory) -> None:
    """Путь вида //host тоже уводит запрос на чужой адрес и запрещён."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    with pytest.raises(ValueError, match=RELATIVE_PATH_ONLY):
        client.endpoint("//evil.example/steal")


def test_parent_traversal_is_rejected(new_client: SyncClientFactory) -> None:
    """Путь не может выйти вверх за пределы суффикса."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    with pytest.raises(ValueError, match=NO_PARENT_TRAVERSAL):
        client.endpoint("../../admin")


def test_parent_traversal_in_the_middle_is_rejected(new_client: SyncClientFactory) -> None:
    """Выход вверх запрещён и в середине пути, а не только в начале."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    with pytest.raises(ValueError, match=NO_PARENT_TRAVERSAL):
        client.endpoint("orders/../../admin")


def test_percent_encoded_traversal_is_rejected(new_client: SyncClientFactory) -> None:
    """Выход вверх, записанный в percent-encoding, тоже должен отвергаться."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    with pytest.raises(ValueError, match=NO_PARENT_TRAVERSAL):
        client.endpoint("%2e%2e/%2e%2e/admin")


def test_percent_encoded_slash_does_not_hide_parent_traversal(new_client: SyncClientFactory) -> None:
    client = new_client("https://files.example", cls=ClientWithTrailingSlash)

    with pytest.raises(ValueError, match=NO_PARENT_TRAVERSAL):
        client.endpoint("orders%2f%2E%2E%2Fadmin")
