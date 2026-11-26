from queue import Queue
from socket import socket
from socketserver import BaseRequestHandler, TCPServer

from wsproto import ConnectionType, WSConnection
from wsproto.events import AcceptConnection, BytesMessage, CloseConnection, Ping, RejectConnection, Request, TextMessage


class WebSocketServer(TCPServer):
    def __init__(self) -> None:
        """Listen on an available loopback port."""
        self.handshakes: Queue[Request] = Queue()
        self.close_codes: Queue[int] = Queue()
        super().__init__(("127.0.0.1", 0), _WebSocketHandler)
        self.url = f"ws://127.0.0.1:{self.server_address[1]}"


class _WebSocketHandler(BaseRequestHandler):
    request: socket
    server: WebSocketServer

    def handle(self) -> None:
        connection = WSConnection(ConnectionType.SERVER)
        self.request.settimeout(5)
        while data := self.request.recv(65536):
            connection.receive_data(data)
            for event in connection.events():
                if isinstance(event, Request):
                    self.server.handshakes.put(event)
                    if event.target.partition("?")[0] != "/ws":
                        self.request.sendall(connection.send(RejectConnection(status_code=403)))
                        return
                    selected = next(iter(event.subprotocols), None)
                    self.request.sendall(connection.send(AcceptConnection(subprotocol=selected)))
                elif isinstance(event, (TextMessage, BytesMessage)):
                    self.request.sendall(connection.send(event))
                elif isinstance(event, Ping):
                    self.request.sendall(connection.send(event.response()))
                elif isinstance(event, CloseConnection):
                    self.server.close_codes.put(event.code)
                    self.request.sendall(connection.send(event.response()))
                    return
