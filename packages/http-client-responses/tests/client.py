from typing import cast

from http_client import AsyncHttpClient, HttpClient
from http_client_responses import GenericResponse, JsonResponse
from httpx import Response

from .models import ExampleRequest, ExampleResponse


def parse_details(response: Response) -> dict[str, str]:
    """Разобрать построчный ответ вида `ключ: значение` в словарь."""
    result: dict[str, str] = {}
    for line in response.text.split("\n"):
        key, value = line.split(":", maxsplit=1)
        result[key] = value.strip()
    return result


class ExampleClient(HttpClient):
    """Тестовый HTTP-клиент."""

    def get_users(self, request: ExampleRequest) -> JsonResponse[ExampleResponse]:
        """Отправить простой get запрос на получение списка пользователей в JSON формате."""
        response = self.get(
            url="/users",
            params=cast("dict[str, str | int]", request.model_dump(exclude_none=True)),
        )
        return JsonResponse(
            response=response,
            schema=ExampleResponse,
        )

    def download_details(self, user_id: int) -> GenericResponse[dict[str, str]]:
        """Отправить запрос, получающий строковые данные, которые будут преобразованы в dict."""
        response = self.get(f"/user/{user_id}/details")
        return GenericResponse(
            response=response,
            parser=parse_details,
        )


class AsyncExampleClient(AsyncHttpClient):
    """Тестовый асинхронный HTTP-клиент."""

    async def get_users(self, request: ExampleRequest) -> JsonResponse[ExampleResponse]:
        """Отправить простой get запрос на получение списка пользователей в JSON формате."""
        response = await self.get(
            url="/users",
            params=cast("dict[str, str | int]", request.model_dump(exclude_none=True)),
        )
        return JsonResponse(
            response=response,
            schema=ExampleResponse,
        )

    async def download_details(self, user_id: int) -> GenericResponse[dict[str, str]]:
        """Отправить запрос, получающий строковые данные, которые будут преобразованы в dict."""
        response = await self.get(f"/user/{user_id}/details")
        return GenericResponse(
            response=response,
            parser=parse_details,
        )
