from collections.abc import Callable

from mcp_client.custom_types import AsyncConnectionHandler

type ConnectionHandlerFactory = Callable[[], AsyncConnectionHandler]
