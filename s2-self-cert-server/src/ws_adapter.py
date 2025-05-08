from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState
from connectivity.connection_adapter import ConnectionAdapter, ConnectionClosed, ConnectionError


class FastAPIWebSocketAdapter(ConnectionAdapter[str]):
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket

    async def receive(self) -> str:
        try:
            data = await self.websocket.receive_text()
            return data
        except WebSocketDisconnect:
            raise ConnectionClosed("Websocket is closed.")
        except RuntimeError as e:
            # Starlette raises RuntimeError if the connection is closed
            raise ConnectionClosed(f"Websocket is closed: {e}")
        except Exception as e:
            raise ConnectionError(f"Unknown websocket error: {e}")

    async def send(self, message: str):
        try:
            await self.websocket.send_text(message)
        except RuntimeError as e:
            # Starlette raises RuntimeError if the connection is closed
            raise ConnectionClosed(f"Websocket is closed: {e}")
        except Exception as e:
            raise ConnectionError(f"Unknown websocket error: {e}")

    @property
    async def open(self) -> bool:
        return self.websocket.application_state == WebSocketState.CONNECTED

    async def close(self, code: int = 1000, reason: str = ""):
        try:
            await self.websocket.close(code=code)
        except Exception as e:
            raise ConnectionError(f"Error closing websocket: {e}")
