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
from websockets.asyncio.client import connect
from connectivity.channel import Channel
from testsuites.server_websocket_envelope_channel import (
    ServerWebsocketConnectionChannel,
)
from testsuites.certification_executor import AbstractCertificationExecutor
from connectivity.s2_channel import S2Channel
from connectivity.config import Config
from connectivity.connection_adapter import ConnectionAdapter
from ws_adapter import WebSocketConnectionAdapter


from testsuites.envelope_models import (
    ServerMessageEnvelope,
    ClientInfo,
    ClientInfoControlMessage,
    ConfigControlMessage,
    ReportControlMessage,
    ControlMessageEnvelope,
)
from importlib.metadata import version


logger = logging.getLogger(__name__)

SERVER_PROTOCOL = os.environ.get("CERTIFICATION_SERVER_PROTOCOL", "ws")
SERVER_HOST = os.environ.get("CERTIFICATION_SERVER_HOST", "localhost")
SERVER_PORT = os.environ.get("CERTIFICATION_SERVER_PORT", "8001")
SERVER_PATH = os.environ.get("CERTIFICATION_SERVER_PORT", "/ws")


class CertificationTestExecutor(AbstractCertificationExecutor):
    config: Config

    report: Optional[ComplianceReport] = None

    def __init__(self, config: Config):
        super().__init__()

        self.config = config

        self.add_handler(ReportControlMessage, self.handle_report_control_message)

    async def handle_report_control_message(self, message: ReportControlMessage):

        report: ComplianceReport = message.report

        logger.info("Received report from server: %s", report)

        self.report = report

    async def connect_to_server(self) -> Channel[ServerMessageEnvelope, str]:
        uri = f"{SERVER_PROTOCOL}://{SERVER_HOST}:{SERVER_PORT}{SERVER_PATH}"
        logger.info(f"Connecting to server ({uri})...")

        ws = await connect(uri)

        connection = WebSocketConnectionAdapter(ws)
        channel = ServerWebsocketConnectionChannel(connection)

        logger.info("Connected to server.")

        return channel

    async def send_client_info_message(self):
        """Sends information about the client to the server. Currently only checks package version but in future can be used for other information."""
        logger.info("* Sending Client Details to Server *")
        logger.debug("Testing Package Version: %s", version("test-suites"))
        logger.debug("Connectivity Package Version: %s", version("connectivity"))

        message = ClientInfoControlMessage(
            client_info=ClientInfo(
                connectivity_version=version("connectivity"),
                testsuites_version=version("test-suites"),
            )
        )

        envelope = ControlMessageEnvelope(message=message)

        self.server_channel.send(envelope)

    async def main_loop(self):

        await self.send_client_info_message()
        await self.send_server_control_message(ConfigControlMessage(config=self.config))

        logger.info("Config sent.")

    async def run(self, s2_channel, *args, **kwargs):
        server_channel = await self.connect_to_server()

        return await super().run(s2_channel, server_channel, *args, **kwargs)


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
