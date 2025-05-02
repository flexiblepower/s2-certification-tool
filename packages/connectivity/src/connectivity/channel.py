import asyncio

import logging

from .connection_adapter import (
    ConnectionAdapter,
    ConnectionClosed,
    ConnectionError,
    ConnectionProtocolError,
)


logger = logging.getLogger(__name__)


class ChannelSendError:
    pass


class Channel:
    connection: ConnectionAdapter
    message_queue: asyncio.Queue
    _stop_event: asyncio.Event

    def __init__(self, connection: ConnectionAdapter) -> None:
        self.connection = connection

        self._stop_event = asyncio.Event()

        self.message_queue = asyncio.Queue()

    async def get_next_message(self) -> str:
        """Pops the next message off the queue to be processed."""
        return await self.message_queue.get()

    async def send(self, message: str):
        return await self.connection.send(message)

    async def receive(self) -> str:
        return await self.connection.receive()

    async def process_received_message(self, message: str):
        await self.message_queue.put(message)

    async def receive_messages(self):
        logger.debug("WebSocket Channel has started to receive messages.")

        try:
            while not self._stop_event.is_set():
                # Timeout was added so that this task can exit at some point since if it never receives another message it just sits waiting.
                try:
                    message = await asyncio.wait_for(self.receive(), timeout=1)
                except asyncio.TimeoutError:
                    continue

                await self.process_received_message(message)
        except ConnectionClosed:
            await self.stop()
        except ConnectionError as e:
            logger.error("Error whilst receive message from WS: %s", str(e))
            await self.stop()
        except asyncio.CancelledError:
            logger.warning("Cancelled error.")

    async def run(self):
        await self.receive_messages()

    async def stop(self):
        self._stop_event.set()

        if await self.connection.open:
            await self.connection.close()
