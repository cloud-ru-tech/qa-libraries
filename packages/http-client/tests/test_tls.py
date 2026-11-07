import ssl
from collections.abc import Iterator
from pathlib import Path
from threading import Thread

import httpx
import pytest
from assertpy import assert_that
from http_client import options
from http_client.client import AsyncHttpClient

from .support.clients import AsyncClientFactory, SyncClientFactory
from .support.tls import TlsServer, generate_certificate, serve_tls


@pytest.fixture()
def tls_server(tmp_path: Path) -> Iterator[TlsServer]:
    certificate, key = generate_certificate(tmp_path)
    with serve_tls(certificate, key) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield TlsServer(f"https://127.0.0.1:{server.server_port}", certificate)
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_sync_client_rejects_untrusted_certificate(tls_server: TlsServer, new_client: SyncClientFactory) -> None:
    client = new_client(tls_server.url)

    with pytest.raises(httpx.ConnectError):
        client.get("/")


async def test_async_client_rejects_untrusted_certificate(
    tls_server: TlsServer, new_async_client: AsyncClientFactory
) -> None:
    client = new_async_client(tls_server.url)

    with pytest.raises(httpx.ConnectError):
        await client.get("/")


def test_verify_context_disables_verification_in_sync_client(
    tls_server: TlsServer, new_client: SyncClientFactory
) -> None:
    client = new_client(tls_server.url, options.with_verify_context(verify=False))

    assert_that(client.get("/").text).is_equal_to("verified TLS transport")


async def test_verify_context_disables_verification_in_async_client(
    tls_server: TlsServer, new_async_client: AsyncClientFactory
) -> None:
    client = new_async_client(tls_server.url, options.with_verify_context(verify=False))

    assert_that((await client.get("/")).text).is_equal_to("verified TLS transport")


async def test_async_client_uses_supplied_ssl_context(
    tls_server: TlsServer, new_async_client: AsyncClientFactory
) -> None:
    context = ssl.create_default_context(cafile=str(tls_server.certificate))
    client = new_async_client(tls_server.url, options.with_verify_context(verify=context))

    assert_that((await client.get("/")).text).is_equal_to("verified TLS transport")


def test_sync_client_uses_supplied_ssl_context(tls_server: TlsServer, new_client: SyncClientFactory) -> None:
    context = ssl.create_default_context(cafile=str(tls_server.certificate))
    client = new_client(tls_server.url, options.with_verify_context(verify=context))

    assert_that(client.get("/").text).is_equal_to("verified TLS transport")


def test_ca_bundle_path_trusts_its_certificate(tls_server: TlsServer, new_client: SyncClientFactory) -> None:
    client = new_client(tls_server.url, options.with_verify_context(verify=str(tls_server.certificate)))

    assert_that(client.get("/").text).is_equal_to("verified TLS transport")


async def test_async_ca_bundle_path_trusts_its_certificate(
    tls_server: TlsServer, new_async_client: AsyncClientFactory
) -> None:
    client = new_async_client(tls_server.url, options.with_verify_context(verify=str(tls_server.certificate)))

    assert_that((await client.get("/")).text).is_equal_to("verified TLS transport")


def test_truststore_rejects_untrusted_certificate(tls_server: TlsServer, new_client: SyncClientFactory) -> None:
    client = new_client(tls_server.url, options.use_truststore())

    with pytest.raises(httpx.ConnectError):
        client.get("/")


async def test_verify_context_applies_to_subclassed_async_client(
    tls_server: TlsServer, new_async_client: AsyncClientFactory
) -> None:
    class ReportsClient(AsyncHttpClient):
        DEFAULT_URL_SUFFIX = "/u-api/reports/v1/"

    client = new_async_client(tls_server.url, options.with_verify_context(verify=False), cls=ReportsClient)

    assert_that((await client.get("/")).text).is_equal_to("verified TLS transport")
