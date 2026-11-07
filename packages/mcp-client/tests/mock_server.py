from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import TYPE_CHECKING, cast

import mcp.server.session
import uvicorn
from mcp import types
from mcp.server.fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from collections.abc import Callable

EXPECTED_TOOL_NAMES = [
    "add",
    "subtract",
    "multiply",
    "divide",
    "fail_tool",
    "echo_with_metadata",
    "slow_tool",
    "echo_arguments_and_metadata",
    "echo_arguments_and_metadata_structured",
    "crash_server",
]
app = cast("Callable[[str], FastMCP[None]]", FastMCP)("TestServer")


class ToolFailureError(RuntimeError):
    pass


def add(a: int, b: int) -> int:
    return a + b


def subtract(a: int, b: int) -> int:
    return a - b


def multiply(a: int, b: int) -> int:
    return a * b


def divide(a: int, b: int) -> float:
    return a / b


def fail_tool() -> str:
    raise ToolFailureError


def echo_with_metadata(message: str, metadata: dict[str, object] | None = None) -> dict[str, object]:
    return {"message": message, "received_metadata": metadata or {}}


async def slow_tool(duration_seconds: float) -> str:
    await asyncio.sleep(duration_seconds)
    return f"Slept for {duration_seconds} seconds"


def echo_arguments_and_metadata(
    arguments: dict[str, object] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {"received_arguments": arguments or {}, "received_metadata": metadata or {}}


def echo_arguments_and_metadata_structured(
    ctx: Context[mcp.server.session.ServerSession, object, object],
    arguments: dict[str, object] | None = None,
) -> types.CallToolResult:
    request_metadata = ctx.request_context.meta
    metadata = cast("dict[str, object]", request_metadata.model_dump(exclude_none=True)) if request_metadata else {}
    result = {"received_arguments": arguments or {}, "received_metadata": metadata}
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(result))],
        structuredContent=result,
        _meta=metadata or None,
    )


def crash_server() -> str:
    os._exit(1)


def register[**P, R](tool: Callable[P, R]) -> None:
    cast("Callable[[Callable[P, R]], None]", app.add_tool)(tool)


register(add)
register(subtract)
register(multiply)
register(divide)
register(fail_tool)
register(echo_with_metadata)
register(slow_tool)
register(echo_arguments_and_metadata)
register(echo_arguments_and_metadata_structured)
register(crash_server)


def serve_http(port: int) -> None:
    config = uvicorn.Config(app.streamable_http_app(), host="127.0.0.1", port=port, log_level="error")
    asyncio.run(uvicorn.Server(config).serve())


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "stdio":
        app.run()
    else:
        port = int(sys.argv[2])
        serve_http(port)
