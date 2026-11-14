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
    """Decorate synchronous send to wrap sending in an Allure step.

    Open the step before sending so it records the request duration,
    and create a failed step for connection errors or timeouts.
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
                    # Read the body inside the step: a lazy generator can fail,
                    # and without a step the report would remain entirely empty
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
    """Decorate asynchronous send to wrap sending in an Allure step.

    Unlike the synchronous version, do not keep the step open across await: Allure stores
    the current step globally, so concurrent requests would attach data
    to the wrong steps. As a tradeoff, asynchronous report steps do not show request duration.
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
                # Read the body inside try: a lazy generator can fail,
                # and without a step the report would remain entirely empty
                body = await _arequest_body(request, settings, streaming=stream)
                response = await func(
                    request,
                    stream=stream,
                    auth=auth,
                    follow_redirects=follow_redirects,
                    anonymous=anonymous,
                )
            except BaseException:
                # Raise inside the step; otherwise Allure closes it without an error and marks it as passed
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
    """Decorate synchronous stream_request to wrap the stream in an Allure step.

    Do not read the streaming response body: attach a placeholder or the data
    the caller has already read inside the step.
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
    """Decorate asynchronous stream_request to wrap the stream in an Allure step.

    Create the step after closing the stream so it does not stay open while awaiting
    caller code; otherwise concurrent streams attach data to the wrong steps.
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
                # Raise inside the step; otherwise Allure closes it without an error and marks it as passed
                with allure.step(step_message):
                    _attach_stream(request, response, body, settings)
                    raise
            else:
                with allure.step(step_message):
                    _attach_stream(request, response, body, settings)

        return wrapper

    return decorator


def _request_body(request: httpx.Request, settings: StepSettings, *, streaming: bool) -> bytes | None:
    """Read the request body before sending while the stream is known to be intact."""
    if not settings.attach_request:
        return None

    if streaming:
        return peek_request_body(request)

    return read_request_body(request)


async def _arequest_body(request: httpx.Request, settings: StepSettings, *, streaming: bool) -> bytes | None:
    """Asynchronous version of _request_body."""
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
    """Attach streaming request and response data to an open step.

    Also call this on failures: if the caller failed inside the stream,
    response data is especially useful in the report.
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
    """Attach data without allowing reporting errors to change the request result.

    Build attachments after sending: the request may have reached the server successfully, and the caller
    could mistake a failure here for a network error and retry the operation.
    Include only the exception class in the message: its text may expose
    body fragments or URLs in the report.
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
    """Build a step title without letting masking errors prevent sending."""
    try:
        return build_step_message(request, settings)
    except Exception:  # noqa: BLE001
        return f"[{request.method}] {request.url.path}"
