import pytest
from assertpy import assert_that
from http_client.client import HttpClient

from .support.clients import SyncClientFactory

# Error messages are part of the endpoint() contract: the test uses them to identify
# which check failed.
RELATIVE_PATH_ONLY = "только относительный путь"
NO_PARENT_TRAVERSAL = "выход вверх по пути"


class ClientWithTrailingSlash(HttpClient):
    DEFAULT_URL_SUFFIX = "/u-api/orders/v1/"


class ClientWithoutTrailingSlash(HttpClient):
    DEFAULT_URL_SUFFIX = "/u-api/orders/v1"


def test_suffix_with_trailing_slash_is_prepended(new_client: SyncClientFactory) -> None:
    """A suffix with a trailing slash is applied in full."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    url = client.endpoint("orders/123")

    assert_that(url).is_equal_to("/u-api/orders/v1/orders/123")


def test_suffix_without_trailing_slash_keeps_last_segment(new_client: SyncClientFactory) -> None:
    """A suffix without a trailing slash retains its last segment.

    Regression: urljoin treated "v1" as a filename and discarded it,
    producing /u-api/orders/orders/123.
    """
    client = new_client("https://example.com", cls=ClientWithoutTrailingSlash)

    url = client.endpoint("orders/123")

    assert_that(url).is_equal_to("/u-api/orders/v1/orders/123")


def test_leading_slash_in_path_is_stripped(new_client: SyncClientFactory) -> None:
    """A leading slash in the path does not affect the result."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    url = client.endpoint("/orders/123")

    assert_that(url).is_equal_to("/u-api/orders/v1/orders/123")


def test_empty_path_returns_suffix(new_client: SyncClientFactory) -> None:
    """An empty path returns the suffix itself."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    url = client.endpoint("")

    assert_that(url).is_equal_to("/u-api/orders/v1/")


def test_empty_suffix_returns_path_unchanged(new_client: SyncClientFactory) -> None:
    """Return the path itself when there is no suffix."""
    client = new_client("https://example.com")

    url = client.endpoint("/orders/123")

    assert_that(url).is_equal_to("orders/123")


def test_absolute_url_is_rejected(new_client: SyncClientFactory) -> None:
    """An absolute URL cannot replace the client base address."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    with pytest.raises(ValueError, match=RELATIVE_PATH_ONLY):
        client.endpoint("https://evil.example/steal")


def test_protocol_relative_url_is_rejected(new_client: SyncClientFactory) -> None:
    """A //host path also redirects the request to another address and is forbidden."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    with pytest.raises(ValueError, match=RELATIVE_PATH_ONLY):
        client.endpoint("//evil.example/steal")


def test_parent_traversal_is_rejected(new_client: SyncClientFactory) -> None:
    """The path cannot traverse above the suffix."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    with pytest.raises(ValueError, match=NO_PARENT_TRAVERSAL):
        client.endpoint("../../admin")


def test_parent_traversal_in_the_middle_is_rejected(new_client: SyncClientFactory) -> None:
    """Parent traversal is forbidden within the path as well as at its start."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    with pytest.raises(ValueError, match=NO_PARENT_TRAVERSAL):
        client.endpoint("orders/../../admin")


def test_percent_encoded_traversal_is_rejected(new_client: SyncClientFactory) -> None:
    """Reject percent-encoded parent traversal as well."""
    client = new_client("https://example.com", cls=ClientWithTrailingSlash)

    with pytest.raises(ValueError, match=NO_PARENT_TRAVERSAL):
        client.endpoint("%2e%2e/%2e%2e/admin")


def test_percent_encoded_slash_does_not_hide_parent_traversal(new_client: SyncClientFactory) -> None:
    client = new_client("https://files.example", cls=ClientWithTrailingSlash)

    with pytest.raises(ValueError, match=NO_PARENT_TRAVERSAL):
        client.endpoint("orders%2f%2E%2E%2Fadmin")
