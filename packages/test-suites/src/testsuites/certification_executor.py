import abc
import asyncio
from typing import (
    Callable,
    Dict,
    Generic,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
)
from connectivity.async_task_manager import AsyncTaskManager

from connectivity.config import Config
from connectivity.channel import Channel
from s2python.message import S2Message
from testsuites.envelope_models import (
    ServerMessageEnvelope,
    S2MessageEnvelope,
    LogMessage,
    LogMessageEnvelope,
    ControlMessage,
    ControlMessageEnvelope,
)

from connectivity.connection_adapter import (
    ConnectionAdapter,
    ConnectionClosed,
    ConnectionError,
    ConnectionProtocolError,
)

import logging

from testsuites.test_executor import AbstractExecutor
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


class AbstractCertificationExecutor(AbstractExecutor, MessageHandler[ControlMessage]):

    s2_channel: Channel[str, str]
    server_channel: Channel[ServerMessageEnvelope, str]

    config: Optional[Config]

    _stop_event: asyncio.Event

    def __init__(self):
        super().__init__()

        # ! Control message handlers
        self.handlers: Dict[Type[ControlMessage], Callable] = {}

        self._stop_event = asyncio.Event()

        self.running = False

    async def main_loop(self):
        logger.info("Starting Main Loop.")
        if self.s2_channel is None or self.server_channel:
            raise ValueError("Channel not set.")

    async def handle_control_message(self, message: ControlMessage):
        await self.handle_message(message)

    async def process_server_message(self, message: ServerMessageEnvelope):
        if type(message) == S2MessageEnvelope:
            await self.s2_channel.send(message.message)
        elif type(message) == LogMessageEnvelope:
            # ? Great variable naming right there...
            logger.info(message.message.message)
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
        except ConnectionClosed:
            # Exit when channel has been closed.
            pass
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

    async def send_server_log_message(
        self,
        message: str,
        details: Optional[str] = None,
        level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO",
    ):
        log_message = LogMessage(level=level, message=message, details=details)
        envelope = LogMessageEnvelope(message=log_message)
        await self.server_channel.send(envelope)

    async def get_next_s2_channel_message(self):
        # Done like this so the server side can override this.
        return await self.s2_channel.get_next_message()

    async def setup(
        self,
        s2_channel: Channel[str, str],
        server_channel: Channel[ServerMessageEnvelope, str],
        *args,
        **kwargs,
    ):
        self._stop_event.clear()

        self.s2_channel = s2_channel
        self.server_channel = server_channel

    def create_tasks(self, tg: asyncio.TaskGroup):
        tg.create_task(self.main_loop(), name="MainLoop")

        tg.create_task(self.s2_channel.run(), name="S2ChannelRun")
        tg.create_task(self.server_channel.run(), name="ServerChannelRun")

        tg.create_task(
            self.process_received_message(
                self.get_next_s2_channel_message, self.process_rm_message
            ),
            name="ProcessRMMessages",
        )
        tg.create_task(
            self.process_received_message(
                self.server_channel.get_next_message, self.process_server_message
            ),
            name="ProcessServerMessages",
        )

    async def cleanup(self, *args, **kwargs):
        pass

    async def stop(self):
        if self._stop_event.is_set():
            return

        logger.debug("Stop Called in class %s", self.__class__.__name__)
        self._stop_event.set()

        if self.s2_channel is not None:
            await self.s2_channel.stop()

        if self.server_channel is not None:
            await self.server_channel.stop()

    async def run(
        self,
        s2_channel: Optional[Channel[str, str]],
        server_channel: Optional[Channel[ServerMessageEnvelope, str]],
        *args,
        **kwargs,
    ):

        self.running = True

        if s2_channel is None or server_channel is None:
            logger.error(
                "Channel not initialized before run, cannot start channel.run task."
            )
            await self.stop()
            self.running = False
            return

        await self.setup(s2_channel, server_channel, *args, **kwargs)

        try:
            async with asyncio.TaskGroup() as tg:

                self.create_tasks(tg)

                logger.info("IntegrationTestExecutor TaskGroup completed successfully.")

        except* Exception as eg:  # Catches one or more exceptions from tasks
            logger.error(
                f"ExceptionGroup caught in IntegrationTestExecutor run: {len(eg.exceptions)} exceptions"
            )
            for i, exc in enumerate(eg.exceptions):
                logger.error(
                    f"  Exception {i+1}/{len(eg.exceptions)} in TaskGroup:",
                    exc_info=exc,
                )
            await self.stop()  # Signal cooperative shutdown for other parts if any
        # except asyncio.CancelledError:
        #     logger.warning("IntegrationTestExecutor run method was cancelled externally.")
        #     self.stop()
        finally:
            logger.info("Certification Test Executor run method finishing.")
            await self.cleanup()  # Perform final cleanup (e.g., channel.stop())
            logger.info("Cleanup finished.")
            self.running = False

    @abc.abstractmethod
    def get_compliance_report(self):
        pass
