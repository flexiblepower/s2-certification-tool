import asyncio
import json
import logging
import os
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


from s2testing.connection import BaseConnection, ServerConnection
from s2testing.async_task_manager import AsyncTaskManager
from s2testing.orchestrator import Orchestrator
from s2testing.connection import SendOkay
from s2testing.controllers import Controller
from s2testing.test_suite.test_suite import TestSuite
from s2testing.util import wait_for_event_or_stop
from s2testing.server_models import (
    ServerMessageEnvelope,
    MessageEnvelopeTypeEnum,
    ControlMessage,
)
from websockets.asyncio.client import connect

logger = logging.getLogger(__name__)


class ServerOrchestrator(Orchestrator):
    connection: Optional["BaseConnection"] = None
    server_connection: Optional["ServerConnection"] = None

    def __init__(
        self,
    ) -> None:
        super().__init__()

    async def process_message(self, message: str):
        # Processes the message that was popped off the `connection`. Will only be S2 Messages.
        # Therefore just send the S2 Message on with the server connection
        try:
            # msg_dict: dict = json.loads(message)
            await self.server_connection.send_s2_message(message)
        except json.JSONDecodeError:
            logger.exception("Received malformed JSON.")

    async def handle_control_message(message: ControlMessage):
        logger.info("Control Message: %s", message)

    async def process_server_message(self, envelope: ServerMessageEnvelope):
        match envelope.message_type:
            case MessageEnvelopeTypeEnum.LOG:
                # TODO: Maybe allow log level changes?
                logger.info(envelope.message.content)
            case MessageEnvelopeTypeEnum.S2:
                await self.connection.send(envelope.message)
            case MessageEnvelopeTypeEnum.CONTROL:
                await self.handle_control_message(envelope.message)

    async def process_server_received_messages(self):
        """AsyncIO task which pops messages off the queue and processes them using the control type."""

        if self.server_connection is None:
            raise ValueError("Server Connection not set.")

        try:
            while not self._stop_event.is_set():
                try:
                    # Use a timeout to periodically check for cancellation
                    message = await asyncio.wait_for(
                        self.server_connection.get_next_message(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue  # Check stop event and loop again

                await self.process_server_message(message)
        except asyncio.CancelledError:
            logger.info("Message receiver cancelled.")
        except Exception as e:
            logger.exception("Message processor encountered an error: %s", e)
        finally:
            await self.stop()

    async def server_connection_receive_messages(self):
        """Wrapping the receive messages method to allow catching of validation errors."""

        if self.server_connection is None:
            raise ValueError("Server connection not set.")

        await self.server_connection.receive_messages()

    async def setup(self, connection, server_connection, *args, **kwargs):
        await super().setup(connection, *args, **kwargs)

        self.server_connection = server_connection

        self.create_task(self.server_connection_receive_messages())
        self.create_task(self.process_server_received_messages())

    async def main_loop(self):
        pass
