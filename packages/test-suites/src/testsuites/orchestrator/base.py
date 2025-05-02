import abc
import asyncio
import logging
import uuid
from types import CoroutineType
from typing import Awaitable, Callable, Coroutine, Dict, Optional, Type

from s2testing.certificate.certificate import ComplianceReport
from s2python.common import ControlType as ProtocolControlType
from s2python.common import (
    EnergyManagementRole,
    Handshake,
    HandshakeResponse,
    ResourceManagerDetails,
    SelectControlType,
)
from s2python.message import S2Message
from s2python.s2_validation_error import S2ValidationError
from s2python.version import S2_VERSION


from ..connection import BaseConnection
from ..async_task_manager import AsyncTaskManager
from s2testing.connection import SendOkay
from s2testing.controllers import Controller
from s2testing.test_suite.test_suite import TestSuite
from s2testing.util import wait_for_event_or_stop

logger = logging.getLogger(__name__)


class Orchestrator(AsyncTaskManager):
    connection: Optional["BaseConnection"] = None

    @abc.abstractmethod
    async def process_message(self, message):
        """Do something with the message that was popped off the connection's queue"""
        pass

    async def process_received_messages(self):
        """AsyncIO task which pops messages off the queue and processes them using the control type."""

        if self.connection is None:
            raise ValueError("Connection not set.")

        try:
            while not self._stop_event.is_set():
                try:
                    # Use a timeout to periodically check for cancellation
                    message = await asyncio.wait_for(
                        self.connection.get_next_message(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue  # Check stop event and loop again

                await self.process_message(message)
        except asyncio.CancelledError:
            logger.info("Message receiver cancelled.")
        except Exception as e:
            logger.exception("Message processor encountered an error: %s", e)
        finally:
            await self.stop()

    async def connection_receive_messages(self):
        """Wrapping the receive messages method to allow catching of validation errors."""

        if self.connection is None:
            raise ValueError("Connection not set.")

        await self.connection.receive_messages()

    async def setup(self, connection: BaseConnection, *args, **kwargs):
        """
        Sets connection and start tasks:
          1. Receive connection messages. WS receive messages and put on queue
          2. Process received connection messages. Pop message from queue and do something with it.
        """
        await super().setup()
        self.connection = connection

        self.create_task(self.connection_receive_messages(), True)
        self.create_task(self.process_received_messages(), True)

    async def cleanup(self, *args, **kwargs):
        logger.info("Cleanup of Orchestrator")
        await super().cleanup()

        await self.connection.stop()

    async def run(self, *args, **kwargs):
        self.running = True

        await self.setup(*args, **kwargs)

        await self._stop_event.wait()

        await self.cleanup(*args, **kwargs)

        self.running = False
