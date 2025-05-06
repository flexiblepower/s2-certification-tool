from websockets.asyncio.connection import Connection as WSConnection

from websockets.exceptions import ConnectionClosed, WebSocketException
from connectivity.connection_adapter import (
    ConnectionAdapter,
    ConnectionError,
    ConnectionClosed,
    ConnectionProtocolError,
)

import logging

logger = logging.getLogger(__name__)


class WebSocketConnectionAdapter(ConnectionAdapter[str]):
    is_open = True

    def __init__(self, ws_connection: WSConnection):
        self.ws_connection = ws_connection

    async def receive(self) -> str:
        try:
            message = await self.ws_connection.recv()
            logger.debug("Received: %s", message)
            if isinstance(message, bytes):
                return message.decode("utf-8")
            return message
        except ConnectionClosed:
            self.is_open = False
            raise ConnectionClosed("Websocket is closed.")
        except WebSocketException as e:
            raise ConnectionProtocolError(f"Websocket protocol error: {e}")
        except Exception as e:
            raise ConnectionError(f"Unknown websocket error: {e}")

    async def send(self, message: str):
        try:
            logger.debug("Sending: %s", message)
            await self.ws_connection.send(message)
        except ConnectionClosed:
            self.is_open = False
            raise ConnectionClosed("Websocket is closed.")
        except WebSocketException as e:
            raise ConnectionProtocolError(f"Websocket protocol error: {e}")
        except Exception as e:
            raise ConnectionError(f"Unknown websocket error: {e}")

    @property
    async def open(self) -> bool:
        return self.is_open

    async def close(self, code: int = 1000, reason: str = ""):
        try:
            await self.ws_connection.close(code=code, reason=reason)
        except Exception as e:
            raise ConnectionError(f"Error closing websocket: {e}")
