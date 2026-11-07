from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
from typing import cast

from mcp.server import FastMCP

app = cast("Callable[[str], FastMCP[None]]", FastMCP)("EmptyTestServer")

if __name__ == "__main__":
    app.run()
