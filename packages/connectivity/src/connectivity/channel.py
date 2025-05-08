import abc
import asyncio

import json
import logging
from typing import Generic, TypeVar

from connectivity.server_models import (
    MessageEnvelopeTypeEnum,
    ServerMessageEnvelope,
    parse_envelope,
)

from .connection_adapter import (
    ConnectionAdapter,
    ConnectionClosed,
    ConnectionError,
    ConnectionProtocolError,
)


logger = logging.getLogger(__name__)


class ChannelSendError:
    pass


T = TypeVar("T")
RawT = TypeVar("RawT")


class Channel(Generic[T, RawT], abc.ABC):
    connection: ConnectionAdapter[RawT]
    message_queue: asyncio.Queue[T | None]
    _stop_event: asyncio.Event

    def __init__(self, connection: ConnectionAdapter[RawT]) -> None:
        self.connection = connection

        self._stop_event = asyncio.Event()

        self.message_queue = asyncio.Queue()

    async def get_next_message(self) -> T:
        msg = await self.message_queue.get()
        if msg is None:
            raise ConnectionClosed("Channel stopped")
        return msg

    async def send(self, message: T):
        return await self.connection.send(message)  # type: ignore

    async def receive(self) -> RawT:
        return await self.connection.receive()

    async def process_received_message(self, message: RawT):
        await self.message_queue.put(message)  # type: ignore

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
            # logger.error("Error whilst receive message from WS: %s", str(e))
            await self.stop()

    async def run(self):
        await self.receive_messages()

        await self.connection.close()

    async def stop(self):
        if not self._stop_event.is_set():
            self.message_queue.put_nowait(None)
            self._stop_event.set()
            await self.connection.close()


class BaseChannel(Channel[str, str]):
    """A str, str channel."""


class ServerWebsocketConnectionChannel(Channel[ServerMessageEnvelope, str]):
    async def send(self, message: ServerMessageEnvelope):
        str_msg: str = message.model_dump_json()

        return await self.connection.send(str_msg)

    async def process_received_message(self, str_msg: str):

        message = parse_envelope(str_msg)

        await self.message_queue.put(message)
