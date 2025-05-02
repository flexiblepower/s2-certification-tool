import asyncio
import json
import logging
import os
import uuid
from types import CoroutineType
from typing import Awaitable, Callable, Coroutine, Dict, Optional, Type

from testsuites.certificate.certificate import ComplianceReport
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


from connectivity.async_task_manager import AsyncTaskManager
from testsuites.controllers import Controller
from testsuites.test_suite.test_suite import TestSuite
from testsuites.util import wait_for_event_or_stop
from connectivity.server_models import (
    ServerMessageEnvelope,
    MessageEnvelopeTypeEnum,
    ControlMessage,
)
from websockets.asyncio.client import connect

logger = logging.getLogger(__name__)

SERVER_PROTOCOL = os.environ.get("CERTIFICATION_SERVER_PROTOCOL", "ws")
SERVER_HOST = os.environ.get("CERTIFICATION_SERVER_HOST", "localhost")
SERVER_PORT = os.environ.get("CERTIFICATION_SERVER_PORT", "8001")
SERVER_PATH = os.environ.get("CERTIFICATION_SERVER_PORT", "/ws")


# class ServerSideCertificationOrchestrator(ServerOrchestrator):

#     async def handle_control_message(message: ControlMessage):
#         logger.info("Control Message: %s", message)

#     async def main_loop(self):
#         pass

#     async def connect_to_server(self) -> ServerConnection:
#         uri = f"{SERVER_PROTOCOL}://{SERVER_HOST}:{SERVER_PORT}{SERVER_PATH}"
#         logger.info(f"Connecting to server ({uri})...")

#         ws = await connect(uri)

#         server_connection = ServerConnection(ws)

#         logger.info("Connected to server.")

#         return server_connection

#     async def setup(self, connection: BaseConnection, *args, **kwargs):
#         server_connection = await self.connect_to_server()

#         await super().setup(connection, server_connection)

#         logger.info("setup complete")
