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
from testsuites.message_handlers import ControlMessageHandler
from s2python.message import S2Message
from testsuites.certificate.certificate import ComplianceReport
from testsuites.test_logger import AbstractTestLogger
from testsuites.envelope_models import (
    ServerMessageEnvelope,
    S2MessageEnvelope,
    LogMessage,
    LogMessageEnvelope,
    ControlMessage,
    ControlMessageEnvelope,
    CertificationEnvelope,
    CertificationMessage,
)
from testsuites.message_handlers import CertificationMessageHandler

from connectivity.connection_adapter import (
    ConnectionClosed,
)

import logging

from testsuites.test_executor import AbstractExecutor

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Message type
H = TypeVar("H")  # Channel type


class MessageHandlerNotFoundError(Exception):
    pass


class AbstractCertificationExecutor(AbstractExecutor, ControlMessageHandler):

    s2_channel: Channel[str, str]
    server_channel: Channel[ServerMessageEnvelope, str]

    config: Optional[Config]

    _stop_event: asyncio.Event

    test_logger: AbstractTestLogger

    certification_handler: CertificationMessageHandler

    def __init__(self, certification_handler: CertificationMessageHandler):
        super().__init__()

        # ! Control message handlers
        self.handlers: Dict[Type[ControlMessage], Callable] = {}

        self.certification_handler = certification_handler

        self._stop_event = asyncio.Event()

        self.running = False

    async def main_loop(self):
        """This is the main execution task of the certification executor. This should coordinate all the other tasks. 
        Once this function exits it will cause all other tasks to exist."""
        logger.info("Starting Main Loop.")
        if self.s2_channel is None or self.server_channel:
            raise ValueError("Channel not set.")

    async def handle_control_message(self, message: ControlMessage):
        await self.handle_message(message)

    @abc.abstractmethod
    async def handle_log_message(self, message: LogMessage):
        # logger.info(message.message)
        pass

    async def handle_certification_message(self, message: CertificationMessage):
        await self.certification_handler.handle_message(message, self.server_channel)

    async def process_server_message(self, message: ServerMessageEnvelope):
        if type(message) == S2MessageEnvelope:
            await self.s2_channel.send(message.message)
        elif type(message) == LogMessageEnvelope:
            await self.handle_log_message(message.message)
        elif type(message) == ControlMessageEnvelope:
            await self.handle_control_message(message.message)
        elif (type(message)) == CertificationEnvelope:
            await self.handle_certification_message(message.message)

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
        # This is the main execution of this class. It does the setup and then the test executor will run on this thread
        tg.create_task(self.main_loop(), name="MainLoop")

        tg.create_task(self.s2_channel.run(), name="S2ChannelRun")

        # This is the channel that receives messages from the local certifier on the dev's device
        tg.create_task(self.server_channel.run(), name="ServerChannelRun")

        # This task processes messages popped off the outgoing message queue form the integration test executor
        tg.create_task(
            self.process_received_message(
                self.get_next_s2_channel_message, self.process_rm_message
            ),
            name="ProcessRMMessages",
        )

        # This task processes messages popped off the incoming message queue form the local certifier on the dev's machine
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
    async def get_compliance_report(self) -> ComplianceReport:
        pass
