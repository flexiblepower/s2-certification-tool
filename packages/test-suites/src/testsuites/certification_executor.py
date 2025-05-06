import asyncio
from typing import (
    Callable,
    Dict,
    Generic,
    Optional,
    Type,
    TypeVar,
    Union,
)
from connectivity.async_task_manager import AsyncTaskManager

from connectivity.config import Config
from connectivity.channel import Channel
from s2python.message import S2Message
from connectivity.server_models import (
    ServerMessageEnvelope,
    S2MessageEnvelope,
    LogMessage,
    LogMessageEnvelope,
    ControlMessage,
    ControlMessageEnvelope,
)

import logging

from testsuites.certificate.certificate import ComplianceReport

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Message type
H = TypeVar("H")  # Channel type


class MessageHandlerNotFoundError(Exception):
    pass


class MessageHandler(Generic[T]):
    handlers: Dict[Type[T], Callable]
    _accept_unhandled_messages: bool = True

    def __init__(self):
        self.handlers: Dict[Type[T], Callable] = {}

    def add_handler(self, msg_type: Type[T], handler: Callable):
        self.handlers[msg_type] = handler

    async def handle_message(self, message: T, *args, **kwargs):
        try:
            handler = self.handlers[type(message)]
            result = await handler(message, *args, **kwargs)  # type: ignore
            return result
        except KeyError:
            if self._accept_unhandled_messages:
                return
            else:
                raise MessageHandlerNotFoundError(
                    f"Command does not exist for message type '{getattr(message, 'message_type', type(message))}'"
                )


class ControlMessageHandler(MessageHandler[ControlMessage]):

    def __init__(self):
        super().__init__()


class AbstractCertificationExecutor(MessageHandler[ControlMessage], AsyncTaskManager):

    s2_channel: Channel[str, str]
    server_channel: Channel[ServerMessageEnvelope, str]

    config: Optional[Config]

    report: ComplianceReport

    def __init__(self):
        super().__init__()

        self.handlers: Dict[Type[ControlMessage], Callable] = {}

    async def main_loop(self):
        logger.info("Starting Main Loop.")
        if self.s2_channel is None or self.server_channel:
            raise ValueError("Channel not set.")

    async def handle_control_message(self, message: ControlMessage):
        logger.info("Control message: %s", message)

    async def process_server_message(self, message: ServerMessageEnvelope):
        if type(message) == S2MessageEnvelope:
            await self.s2_channel.send(message.message)
        elif type(message) == LogMessageEnvelope:
            logger.info(message.message.content)
        elif type(message) == ControlMessageEnvelope:
            await self.handle_control_message(message.message)

    async def process_rm_message(self, message: str):
        envelope = S2MessageEnvelope(message=message)

        await self.server_channel.send(envelope)

    async def process_received_message(
        self, get_next_message: Callable, process_message: Callable
    ):
        """AsyncIO task which pops messages off the queue and processes them using the control type."""

        try:
            while not self._stop_event.is_set():
                try:
                    # Use a timeout to periodically check for cancellation
                    message = await asyncio.wait_for(get_next_message(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue  # Check stop event and loop again

                await process_message(message)
        except asyncio.CancelledError:
            logger.info("Message Channel cancelled.")
        except Exception as e:
            logger.exception("Message processor encountered an error: %s", e)
        finally:
            await self.stop()

    async def send_server_control_message(self, message: ControlMessage):
        envelope = ControlMessageEnvelope(message=message)
        await self.server_channel.send(envelope)

    async def send_server_s2_message(self, message: Union[str, S2Message]):
        if isinstance(message, S2Message):
            msg_str = message.model_dump_json()
        elif isinstance(message, str):
            msg_str = message
        else:
            raise TypeError(
                f"message must be str or S2Message, got {type(message).__name__}"
            )

        envelope = S2MessageEnvelope(message=msg_str)
        await self.server_channel.send(envelope)

    async def send_s2_message(self, message: str):
        await self.s2_channel.send(message)

    async def send_server_log_message(self, message: LogMessage):
        envelope = LogMessageEnvelope(message=message)
        await self.server_channel.send(envelope)

    async def get_next_s2_channel_message(self):
        # Done like this so the server side can override this.
        return await self.s2_channel.get_next_message()

    def get_compliance_report(self):
        return self.report

    async def setup(
        self,
        s2_channel: Channel[str, str],
        server_channel: Channel[ServerMessageEnvelope, str],
        *args,
        **kwargs,
    ):
        await super().setup()

        self.s2_channel = s2_channel
        self.server_channel = server_channel

        self.create_task(self.main_loop(), False)

        self.create_task(self.s2_channel.run(), False)
        self.create_task(self.server_channel.run(), False)

        self.create_task(
            self.process_received_message(
                self.get_next_s2_channel_message, self.process_rm_message
            ),
            True,
        )
        self.create_task(
            self.process_received_message(
                server_channel.get_next_message, self.process_server_message
            ),
            True,
        )

    async def run(self, s2_channel, *args, **kwargs):
        self.running = True

        await self.setup(s2_channel, *args, **kwargs)

        await self._stop_event.wait()

        await self.cleanup(*args, **kwargs)

        self.running = False
