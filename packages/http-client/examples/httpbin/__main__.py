"""Run all demo scenarios.

Run:
    docker compose up -d
    uv run python -m examples.httpbin
"""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import TYPE_CHECKING, TypedDict, cast

import httpx

from . import settings
from .async_client import build_async_echo_client, build_async_httpbin_client
from .client import build_echo_client, build_httpbin_client
from .decorators import TransportMetrics
from .logging_setup import demo_logger, setup_logging

if TYPE_CHECKING:
    from logging import Logger

    from .async_client import AsyncHttpbinClient
    from .client import HttpbinClient


class SecretPayload(TypedDict):
    """Demo JSON structure with fields to mask."""

    user: dict[str, str]
    items: list[dict[str, str]]
    comment: str


class HeaderEcho(TypedDict):
    """Headers returned by local httpbin."""

    headers: dict[str, str]


class JsonEcho(TypedDict):
    """JSON echo returned by local httpbin."""

    json: SecretPayload


SECRET_PAYLOAD: SecretPayload = {
    "user": {"login": "demo", "password": "s3cret"},
    "items": [{"token": "tok-1"}, {"token": "tok-2"}],
    "comment": "это поле в логе останется как есть",
}


def banner(log: Logger, title: str) -> None:
    """Mark a scenario in the log."""
    log.info("%s", "─" * 100)
    log.info("СЦЕНАРИЙ: %s", title)


def scenario_crud(client: HttpbinClient, log: Logger) -> None:
    """Demonstrate basic methods, each with its own client endpoint method."""
    banner(log, "базовые методы GET/POST/PUT/PATCH/DELETE")
    client.get_echo(page="1", size="20")
    client.post_json({"name": "заказ", "amount": 100})
    client.put_json({"name": "заказ", "amount": 200})
    client.patch_json({"amount": 300})
    client.delete_resource()

    response = client.get_request_headers()
    received = cast("HeaderEcho", response.json())["headers"]
    log.info(
        "Сервис увидел заголовки клиента: X-Client-Name=%s, X-Request-ID и Traceparent на месте: %s",
        received.get("X-Client-Name"),
        {"X-Request-Id", "Traceparent"} <= set(received),
    )


def scenario_masking(client: HttpbinClient, log: Logger) -> None:
    """Mask secrets in request and response logs."""
    banner(log, "маскирование секретов")
    log.info("В теле ниже password и token заменены на ****, а comment виден целиком")
    response = client.post_json(SECRET_PAYLOAD)
    echoed = cast("JsonEcho", response.json())["json"]
    log.info(
        "Сервис получил исходное тело без маскирования: %s",
        echoed == SECRET_PAYLOAD,
    )


def scenario_auth(client: HttpbinClient, log: Logger) -> None:
    """Client Basic authentication and disabling it for one call."""
    banner(log, "авторизация и anonymous=True")
    authorized = client.basic_auth(settings.DEMO_USER, settings.DEMO_PASSWORD)
    log.info("С авторизацией клиента: %s", authorized.status_code)

    anonymous = client.basic_auth(settings.DEMO_USER, settings.DEMO_PASSWORD, anonymous=True)
    log.info("С anonymous=True авторизация не применяется вообще: %s", anonymous.status_code)
    log.info(
        "Пароль виден в пути запроса: так устроен эндпоинт httpbin. "
        "Маскирование работает по заголовкам, query и телу, но не по URL — секретам там не место"
    )


def scenario_redirects(client: HttpbinClient, log: Logger) -> None:
    """Redirects: the client does not follow them, but a call can override this."""
    banner(log, "редиректы")
    kept = client.redirect(3)
    log.info("Без опции with_follow_redirects клиент отдаёт сам редирект: %s", kept.status_code)

    followed = client.redirect(3, follow_redirects=True)
    log.info(
        "С follow_redirects=True на вызове: %s, конечный URL %s, звеньев в истории %s",
        followed.status_code,
        followed.url.path,
        len(followed.history),
    )
    log.info("Декоратор send при этом сработал один раз: цепочку httpx проходит внутри одного вызова")


def scenario_timeout(client: HttpbinClient, log: Logger) -> None:
    """Demonstrate a per-call timeout overriding the client timeout."""
    banner(log, "таймаут")
    fast = client.delay(1, timeout_seconds=5.0)
    log.info("Задержка 1 с при таймауте 5 с: %s", fast.status_code)

    try:
        client.delay(3, timeout_seconds=1.0)
    except httpx.TimeoutException as error:
        log.info("Задержка 3 с при таймауте 1 с — ожидаемое исключение %s", type(error).__name__)


def scenario_errors(client: HttpbinClient, log: Logger) -> None:
    """Error status: the hook warns and raise_for_status raises an exception."""
    banner(log, "ошибка сервера")
    response = client.status(500)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        log.info("raise_for_status поднял %s на статусе %s", type(error).__name__, error.response.status_code)


def scenario_binary(client: HttpbinClient, log: Logger) -> None:
    """Binary body: the logger chooses between logging text and size."""
    banner(log, "бинарный ответ")
    response = client.get_bytes(512)
    log.info("Получено %s байт; в логе тело показано как binary content", len(response.content))


def scenario_streaming(client: HttpbinClient, log: Logger) -> None:
    """Streaming: read the body inside the context manager."""
    banner(log, "стриминг")
    log.info("В логе ответа тело помечено как <streamed content>: на момент хука оно ещё не прочитано")

    with client.stream_lines(3) as response:
        response.raise_for_status()
        lines = [line for line in response.iter_lines() if line]
    log.info("Прочитано строк из потока: %s", len(lines))

    received = 0
    with client.stream_bytes(4096) as response:
        for chunk in response.iter_bytes(chunk_size=1024):
            received += len(chunk)
    log.info("Прочитано байт из потока: %s", received)


def scenario_url_suffix(log: Logger) -> None:
    """Path prefix using DEFAULT_URL_SUFFIX and endpoint()."""
    banner(log, "префикс пути")
    with build_echo_client() as client:
        response = client.ping()
        log.info("endpoint('ping') с суффиксом %s дал путь %s", client.DEFAULT_URL_SUFFIX, response.url.path)

        try:
            client.endpoint("https://example.com/other")
        except ValueError as error:
            log.info("endpoint() не пускает абсолютный URL: %s", type(error).__name__)


def run_sync_demo(metrics: TransportMetrics, log: Logger) -> None:
    """Run the synchronous client scenarios."""
    banner(log, "СИНХРОННЫЙ КЛИЕНТ")
    with build_httpbin_client(metrics) as client:
        scenario_crud(client, log)
        scenario_masking(client, log)
        scenario_auth(client, log)
        scenario_redirects(client, log)
        scenario_timeout(client, log)
        scenario_errors(client, log)
        scenario_binary(client, log)
        scenario_streaming(client, log)
    scenario_url_suffix(log)


async def async_scenario_crud(client: AsyncHttpbinClient, log: Logger) -> None:
    """Access the same endpoints using await."""
    banner(log, "асинхронно: базовые методы")
    await client.get_echo(page="1", size="20")
    await client.post_json(SECRET_PAYLOAD)
    await client.put_json({"amount": 200})
    await client.patch_json({"amount": 300})
    await client.delete_resource()
    await client.get_bytes(512)
    log.info("Синхронные хуки в асинхронном клиенте работают: логи и длительность выше собраны ими")


async def async_scenario_auth(client: AsyncHttpbinClient, log: Logger) -> None:
    """Asynchronous client authentication and disabling it."""
    banner(log, "асинхронно: авторизация")
    authorized = await client.basic_auth(settings.DEMO_USER, settings.DEMO_PASSWORD)
    anonymous = await client.basic_auth(settings.DEMO_USER, settings.DEMO_PASSWORD, anonymous=True)
    log.info("С авторизацией %s, с anonymous=True %s", authorized.status_code, anonymous.status_code)


async def async_scenario_errors(client: AsyncHttpbinClient, log: Logger) -> None:
    """Timeout and error status in the asynchronous client."""
    banner(log, "асинхронно: таймаут и ошибка сервера")
    try:
        await client.delay(3, timeout_seconds=1.0)
    except httpx.TimeoutException as error:
        log.info("Ожидаемое исключение %s", type(error).__name__)

    response = await client.status(503)
    log.info("Статус получен без исключения: %s", response.status_code)


async def async_scenario_streaming(client: AsyncHttpbinClient, log: Logger) -> None:
    """Asynchronous client streaming: use async with without awaiting the method itself."""
    banner(log, "асинхронно: стриминг")
    async with client.stream_lines(3) as response:
        response.raise_for_status()
        lines = [line async for line in response.aiter_lines() if line]
    log.info("Прочитано строк из потока: %s", len(lines))

    received = 0
    async with client.stream_bytes(4096) as response:
        async for chunk in response.aiter_bytes(chunk_size=1024):
            received += len(chunk)
    log.info("Прочитано байт из потока: %s", received)


async def async_scenario_concurrency(client: AsyncHttpbinClient, log: Logger) -> None:
    """Demonstrate concurrent requests, unavailable in the synchronous client."""
    banner(log, "асинхронно: пять запросов параллельно")
    started_at = perf_counter()
    responses = await asyncio.gather(*(client.delay(1, timeout_seconds=5.0) for _ in range(5)))
    log.info(
        "Пять ответов по 1 с получены за %.1f с, статусы %s",
        perf_counter() - started_at,
        [response.status_code for response in responses],
    )


async def async_scenario_url_suffix(log: Logger) -> None:
    """Path prefix in the asynchronous client."""
    banner(log, "асинхронно: префикс пути")
    async with build_async_echo_client() as client:
        response = await client.ping()
        log.info("Путь запроса: %s", response.url.path)


async def run_async_demo(metrics: TransportMetrics, log: Logger) -> None:
    """Run the asynchronous client scenarios."""
    banner(log, "АСИНХРОННЫЙ КЛИЕНТ")
    async with build_async_httpbin_client(metrics) as client:
        await async_scenario_crud(client, log)
        await async_scenario_auth(client, log)
        await async_scenario_errors(client, log)
        await async_scenario_streaming(client, log)
        await async_scenario_concurrency(client, log)
    await async_scenario_url_suffix(log)


def main() -> None:
    """Set up logging and run both clients."""
    setup_logging()
    log = demo_logger()

    sync_metrics = TransportMetrics()
    async_metrics = TransportMetrics()

    run_sync_demo(sync_metrics, log)
    asyncio.run(run_async_demo(async_metrics, log))

    banner(log, "итоги")
    log.info("Синхронный клиент: %s", sync_metrics.summary())
    log.info("Асинхронный клиент: %s", async_metrics.summary())


if __name__ == "__main__":
    main()
