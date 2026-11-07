from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager, suppress
from functools import wraps

import allure
import httpx
from http_client.types import (
    AsyncSendDecorator,
    AsyncSendMethod,
    AsyncStreamRequestDecorator,
    AsyncStreamRequestMethod,
    SyncSendDecorator,
    SyncSendMethod,
    SyncStreamRequestDecorator,
    SyncStreamRequestMethod,
)
from httpx._types import AuthTypes

from .settings import StepSettings
from .utils import (
    Attachment,
    aread_request_body,
    aread_response_body,
    build_step_message,
    parse_request_for_attach,
    parse_response_for_attach,
    parse_response_headers_for_attach,
    peek_request_body,
    peek_response_body,
    read_request_body,
    read_response_body,
)


def step_send_decorator(settings: StepSettings) -> SyncSendDecorator:
    """Декоратор синхронного send, оборачивающий отправку в Allure шаг.

    Шаг открывается до отправки, поэтому в него попадает длительность запроса,
    а при ошибке соединения или таймауте шаг создается и помечается упавшим.
    """

    def decorator(func: SyncSendMethod) -> SyncSendMethod:
        @wraps(func)
        def wrapper(
            request: httpx.Request,
            *,
            stream: bool = False,
            auth: AuthTypes | None = None,
            follow_redirects: bool | None = None,
            anonymous: bool = False,
        ) -> httpx.Response:
            body: bytes | None = None

            with allure.step(_step_message(request, settings)):
                try:
                    # Чтение тела внутри шага: ленивый генератор может упасть,
                    # и тогда без шага отчет остался бы вовсе пустым
                    body = _request_body(request, settings, streaming=stream)
                    response = func(
                        request,
                        stream=stream,
                        auth=auth,
                        follow_redirects=follow_redirects,
                        anonymous=anonymous,
                    )
                except BaseException:
                    _attach_request(request, body, settings)
                    raise

                _attach_request(request, body, settings)
                _attach_response(response, read_response_body(response, streaming=stream), settings)

                return response

        return wrapper

    return decorator


def async_step_send_decorator(settings: StepSettings) -> AsyncSendDecorator:
    """Декоратор асинхронного send, оборачивающий отправку в Allure шаг.

    В отличие от синхронного, шаг не держится открытым на время await: Allure хранит
    текущий шаг глобально, поэтому при одновременных запросах вложения расходились бы
    по чужим шагам. Цена - в асинхронном отчете шаг не показывает длительность запроса.
    """

    def decorator(func: AsyncSendMethod) -> AsyncSendMethod:
        @wraps(func)
        async def wrapper(
            request: httpx.Request,
            *,
            stream: bool = False,
            auth: AuthTypes | None = None,
            follow_redirects: bool | None = None,
            anonymous: bool = False,
        ) -> httpx.Response:
            body: bytes | None = None
            step_message = _step_message(request, settings)

            try:
                # Чтение тела внутри try: ленивый генератор может упасть,
                # и тогда без шага отчет остался бы вовсе пустым
                body = await _arequest_body(request, settings, streaming=stream)
                response = await func(
                    request,
                    stream=stream,
                    auth=auth,
                    follow_redirects=follow_redirects,
                    anonymous=anonymous,
                )
            except BaseException:
                # raise внутри шага, иначе Allure закроет его без ошибки и пометит успешным
                with allure.step(step_message):
                    _attach_request(request, body, settings)
                    raise

            response_body = await aread_response_body(response, streaming=stream)

            with allure.step(step_message):
                _attach_request(request, body, settings)
                _attach_response(response, response_body, settings)

            return response

        return wrapper

    return decorator


def step_stream_decorator(settings: StepSettings) -> SyncStreamRequestDecorator:
    """Декоратор синхронного stream_request, оборачивающий поток в Allure шаг.

    Тело потокового ответа не читается: во вложение попадает заглушка либо то,
    что вызывающий код успел вычитать внутри шага.
    """

    def decorator(func: SyncStreamRequestMethod) -> SyncStreamRequestMethod:
        @wraps(func)
        @contextmanager
        def wrapper(
            request: httpx.Request,
            *,
            anonymous: bool = False,
            auth: AuthTypes | None = None,
            follow_redirects: bool | None = None,
        ) -> Iterator[httpx.Response]:
            body = _request_body(request, settings, streaming=True)
            response: httpx.Response | None = None

            with allure.step(_step_message(request, settings)):
                try:
                    with func(
                        request,
                        anonymous=anonymous,
                        auth=auth,
                        follow_redirects=follow_redirects,
                    ) as opened:
                        response = opened
                        yield opened
                finally:
                    _attach_stream(request, response, body, settings)

        return wrapper

    return decorator


def async_step_stream_decorator(settings: StepSettings) -> AsyncStreamRequestDecorator:
    """Декоратор асинхронного stream_request, оборачивающий поток в Allure шаг.

    Шаг создается после закрытия потока, чтобы не держать его открытым на время await
    вызывающего кода - иначе при одновременных потоках вложения расходятся по чужим шагам.
    """

    def decorator(func: AsyncStreamRequestMethod) -> AsyncStreamRequestMethod:
        @wraps(func)
        @asynccontextmanager
        async def wrapper(
            request: httpx.Request,
            *,
            anonymous: bool = False,
            auth: AuthTypes | None = None,
            follow_redirects: bool | None = None,
        ) -> AsyncIterator[httpx.Response]:
            body = await _arequest_body(request, settings, streaming=True)
            step_message = _step_message(request, settings)
            response: httpx.Response | None = None

            try:
                async with func(
                    request,
                    anonymous=anonymous,
                    auth=auth,
                    follow_redirects=follow_redirects,
                ) as opened:
                    response = opened
                    yield opened
            except BaseException:
                # raise внутри шага, иначе Allure закроет его без ошибки и пометит успешным
                with allure.step(step_message):
                    _attach_stream(request, response, body, settings)
                    raise
            else:
                with allure.step(step_message):
                    _attach_stream(request, response, body, settings)

        return wrapper

    return decorator


def _request_body(request: httpx.Request, settings: StepSettings, *, streaming: bool) -> bytes | None:
    """Прочитать тело запроса до отправки, пока поток заведомо цел."""
    if not settings.attach_request:
        return None

    if streaming:
        return peek_request_body(request)

    return read_request_body(request)


async def _arequest_body(request: httpx.Request, settings: StepSettings, *, streaming: bool) -> bytes | None:
    """Асинхронный вариант _request_body."""
    if not settings.attach_request:
        return None

    if streaming:
        return peek_request_body(request)

    return await aread_request_body(request)


def _attach_stream(
    request: httpx.Request,
    response: httpx.Response | None,
    body: bytes | None,
    settings: StepSettings,
) -> None:
    """Прикрепить данные потокового запроса и ответа к открытому шагу.

    Вызывается и на ошибочном пути: если вызывающий код упал внутри потока,
    данные ответа нужны в отчете тем более.
    """
    _attach_request(request, body, settings)

    if response is not None:
        _attach_response(response, peek_response_body(response), settings)


def _attach_request(request: httpx.Request, body: bytes | None, settings: StepSettings) -> None:
    if not settings.attach_request:
        return

    _attach_safely("Request details", lambda: parse_request_for_attach(request, body, settings), settings)


def _attach_response(response: httpx.Response, body: bytes | None, settings: StepSettings) -> None:
    if settings.attach_response_headers:
        _attach_safely(
            "Response headers",
            lambda: parse_response_headers_for_attach(response, settings),
            settings,
        )

    if settings.attach_response:
        _attach_safely("Response content", lambda: parse_response_for_attach(response, body, settings), settings)


def _attach_safely(name: str, build: Callable[[], Attachment | None], settings: StepSettings) -> None:
    """Прикрепить вложение так, чтобы ошибка отчета не меняла результат запроса.

    Вложение строится уже после отправки: запрос мог успешно уйти на сервер, и падение
    здесь вызывающий код принял бы за сетевую ошибку и мог бы повторить операцию.
    В сообщении остается только класс исключения - его текст способен утащить в отчет
    куски тела или URL.
    """
    try:
        attachment = build()
        if attachment is not None:
            attachment.truncate(settings.max_attach_length).attach()
    except Exception as error:  # noqa: BLE001
        with suppress(Exception):
            Attachment(
                name=name,
                content=f"<Ошибка формирования вложения: {type(error).__name__}>",
                type=allure.attachment_type.TEXT,
            ).attach()


def _step_message(request: httpx.Request, settings: StepSettings) -> str:
    """Собрать заголовок шага, не давая ошибке маскирования сорвать отправку."""
    try:
        return build_step_message(request, settings)
    except Exception:  # noqa: BLE001
        return f"[{request.method}] {request.url.path}"
