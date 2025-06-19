import abc
import asyncio
import logging
from typing import Dict, Optional

from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    Handshake,
)
from s2python.message import S2Message
from testsuites.util import wait_for_event_or_stop
from testsuites.certificate.certificate import ComplianceReport

from connectivity.s2_channel import S2Channel
from connectivity.connection_adapter import ConnectionClosed, ConnectionError
from .role_executors import TestRoleExecutor


logger = logging.getLogger(__name__)


class AbstractExecutor(abc.ABC):

    _stop_event: asyncio.Event

    running = False

    def is_running(self):
        return self.running

    @abc.abstractmethod
    async def run(self, *args, **kwargs):
        pass

    async def stop(self):
        logger.debug("Stop Called in class %s", self.__class__.__name__)
        self._stop_event.set()


class IntegrationTestExecutor(AbstractExecutor):
    """
    Waits for a handshake message to be received and based on the Role value chooses the correct
    RoleExecutor. From that point onwards all messages are passed straight to the role executor.
    The main method of the role executor is executed.
    """

    # The channel which connects to the S2 RM.
    # Has it's own task which needs to be run which received messages from the S2 device and puts them into a queue so they can be processed here.
    # Sending a message to the device is done by calling `send_msg_and_await_reception_status`
    channel: Optional["S2Channel"] = None

    executor: TestRoleExecutor | None = None
    role_executors: Dict[EnergyManagementRole, TestRoleExecutor]

    _stop_event: asyncio.Event

    _select_role_executor = asyncio.Event()

    def __init__(
        self,
        role_executors: Dict[EnergyManagementRole, TestRoleExecutor],
    ) -> None:

        self.role_executors = role_executors

        self._stop_event = asyncio.Event()
        self._select_role_executor = asyncio.Event()

        self.running = False

    async def handle_handshake(self, message: Handshake):
        # On handshake we select the executor based on the role of the connected device.
        role = message.role

        self.executor = self.role_executors[role]
        self.executor.incoming_handshake_message = message

        # Setting this will allow the main_loop to proceed
        self._select_role_executor.set()

    async def process_message(self, message: S2Message):

        if type(message) == Handshake:
            await self.handle_handshake(message)

        # Handle the incoming message with the selected executor
        if self.executor is not None:
            # logger.info("Passing message to executor: %s", message)
            await self.executor.process_message(message)
        else:
            raise ValueError(
                f"Message of type {message.message_type} received before Handshake."
            )

    async def process_received_messages(self):
        """AsyncIO task which pops messages off the queue and processes them using the control type."""

        if self.channel is None:
            raise ValueError("Channel not set.")

        try:
            while not self._stop_event.is_set():
                try:
                    # Use a timeout to periodically check for cancellation. Otherwise this will block the program exiting.
                    message = await asyncio.wait_for(
                        self.channel.get_next_message(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue  # Check stop event and loop again

                await self.process_message(message)
        except asyncio.CancelledError:
            logger.info("Message Channel cancelled.")
        except ConnectionClosed:
            pass
        except Exception as e:
            logger.exception("Message processor encountered an error: %s", e)
            await self.stop()

    def is_running(self):
        return self.running

    async def stop(self):
        await super().stop()

        if self.channel is not None:
            await self.channel.stop()

    async def setup(self, channel: S2Channel, *args, **kwargs):
        self.channel = channel

        self._stop_event.clear()
        self._select_role_executor.clear()

    async def cleanup(self, *args, **kwargs):
        pass

    async def run_channel(self):
        """Wrapper method for the channel.run task for catching errors in it."""
        if self.channel is None:
            raise ValueError("S2 Channel is not provided")
        try:
            await self.channel.run()
        except ConnectionClosed:
            await self.stop()
        except ConnectionError:
            await self.stop()

    async def main_loop(self):
        # Wait until the initial handshake message has been received and role executor set before running the role executor's main loop
        await wait_for_event_or_stop(self._select_role_executor, self._stop_event)

        if self.executor is None or self.channel is None:
            raise ValueError("Unable to run role executor main loop.")

        logger.info("Choosing executor as role %s", self.executor.role)
        # await wait_for_event_or_stop(self._select_role_executor, self._stop_event)
        await self.executor.run(self.channel, self._stop_event)

        await self.stop()

    async def run(self, *args, **kwargs):
        """Main control method of the executor. It creates all of the tasks and manages them."""
        self.running = True
        await self.setup(*args, **kwargs)

        try:
            async with asyncio.TaskGroup() as tg:

                if self.channel is None:
                    logger.error(
                        "Channel not initialized before run, cannot start channel.run task."
                    )
                    await self.stop()
                    self.running = False
                    return

                tg.create_task(self.run_channel(), name="ChannelRun")
                tg.create_task(self.process_received_messages(), name="MessageProcess")
                tg.create_task(self.main_loop(), name="MainLoop")

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
        finally:
            logger.info("IntegrationTestExecutor run method finishing.")
            await self.cleanup()  # Perform final cleanup (e.g., channel.stop())
            logger.info("Cleanup finished.")
            self.running = False

    async def get_compliance_report(self) -> ComplianceReport:
        if self.executor is not None:
            return self.executor.report
        raise ValueError("No testing has been done.")


