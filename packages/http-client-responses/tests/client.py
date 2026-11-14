from typing import cast

from http_client import AsyncHttpClient, HttpClient
from http_client_responses import GenericResponse, JsonResponse
from httpx import Response

from .models import ExampleRequest, ExampleResponse


def parse_details(response: Response) -> dict[str, str]:
    """Parse a line-based `key: value` response into a dictionary."""
    result: dict[str, str] = {}
    for line in response.text.split("\n"):
        key, value = line.split(":", maxsplit=1)
        result[key] = value.strip()
    return result


class ExampleClient(HttpClient):
    """HTTP client for tests."""

    def get_users(self, request: ExampleRequest) -> JsonResponse[ExampleResponse]:
        """Send a simple GET request for a JSON user list."""
        response = self.get(
            url="/users",
            params=cast("dict[str, str | int]", request.model_dump(exclude_none=True)),
        )
        return JsonResponse(
            response=response,
            schema=ExampleResponse,
        )

    def download_details(self, user_id: int) -> GenericResponse[dict[str, str]]:
        """Send a request for string data to be converted to a dict."""
        response = self.get(f"/user/{user_id}/details")
        return GenericResponse(
            response=response,
            parser=parse_details,
        )


class AsyncExampleClient(AsyncHttpClient):
    """Asynchronous HTTP client for tests."""

    async def get_users(self, request: ExampleRequest) -> JsonResponse[ExampleResponse]:
        """Send a simple GET request for a JSON user list."""
        response = await self.get(
            url="/users",
            params=cast("dict[str, str | int]", request.model_dump(exclude_none=True)),
        )
        return JsonResponse(
            response=response,
            schema=ExampleResponse,
        )

    async def download_details(self, user_id: int) -> GenericResponse[dict[str, str]]:
        """Send a request for string data to be converted to a dict."""
        response = await self.get(f"/user/{user_id}/details")
        return GenericResponse(
            response=response,
            parser=parse_details,
        )
