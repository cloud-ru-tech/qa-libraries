from typing import TYPE_CHECKING, cast

from mcp.server import MCPServer

if TYPE_CHECKING:
    from collections.abc import Callable

app = cast("Callable[[str], MCPServer[None]]", MCPServer)("EmptyTestServer")

if __name__ == "__main__":
    app.run()
