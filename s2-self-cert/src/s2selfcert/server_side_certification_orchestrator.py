import asyncio
import logging
from typing import Awaitable, Callable, Coroutine, Dict, Optional, Type

from testsuites.certificate.certificate import ComplianceReport
from websockets.asyncio.client import connect
from connectivity.channel import Channel
from testsuites.server_websocket_envelope_channel import (
    ServerWebsocketConnectionChannel,
)
from testsuites.certification_executor import AbstractCertificationExecutor
from connectivity.config import Config
from s2selfcert.certifier import ClientSideCertifier
from s2selfcert.ws_adapter import WebSocketConnectionAdapter


from testsuites.envelope_models import (
    ServerMessageEnvelope,
    ClientInfo,
    ClientInfoControlMessage,
    ConfigControlMessage,
    ReportControlMessage,
    ControlMessageEnvelope,
)
from testsuites.util import wait_for_event_or_stop
from testsuites.test_suite import TestLogger
from testsuites.test_logger import AbstractTestLogger, TestLogger, ServerTestLogger
from importlib.metadata import version


logger = logging.getLogger(__name__)


class CertificationTestExecutor(AbstractCertificationExecutor):
    config: Config

    report: Optional[ComplianceReport] = None

    test_logger: TestLogger

    _received_report_event: asyncio.Event

    certification_handler: ClientSideCertifier

    def __init__(
        self,
        config: Config,
        test_logger: AbstractTestLogger,
        certification_handler: ClientSideCertifier,
    ):
        super().__init__(certification_handler)

        self.config = config
        self.test_logger = test_logger

        self.add_handler(ReportControlMessage, self.handle_report_control_message)

        self._received_report_event = asyncio.Event()

    async def handle_report_control_message(self, message: ReportControlMessage):

        report: ComplianceReport = message.report

        logger.info("Received report from server: %s", report)

        self.report = report

        self._received_report_event.set()

    async def handle_log_message(self, message):
        if message.logger == "test":
            self.test_logger.log(message.message, message.level, ident=message.ident)
        else:
            logger.info(
                message.message,
            )

    async def connect_to_server(self) -> Channel[ServerMessageEnvelope, str]:
        uri = self.config.certification.uri
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

        await self.server_channel.send(envelope)

    async def main_loop(self):

        await self.send_client_info_message()
        await self.send_server_control_message(ConfigControlMessage(config=self.config))

        await self.certification_handler.send_key_registration_request(
            self.server_channel
        )

        await wait_for_event_or_stop(
            self.certification_handler._challenge_complete_event,
            self._stop_event,
            description="Received Report Event",
        )

        # exit if the challenge failed since it was invalid. Done from other side as well.
        if not self.certification_handler.challenge_status:
            logger.info("Invalid certificate challenge.")
            await self.stop()
            return
        
        logger.info("Certificate Challenge Complete.")

        await wait_for_event_or_stop(
            self.certification_handler._signing_started_event,
            self._stop_event,
            description="Received Report Event",
        )

        logger.info("Testing complete. Signing has started.")

        await wait_for_event_or_stop(
            self.certification_handler._signing_complete_event,
            self._stop_event,
            description="Report Signing Complete Event",
        )

        logger.info("Singing complete!")

    async def run(self, s2_channel, *args, **kwargs):
        server_channel = await self.connect_to_server()

        return await super().run(s2_channel, server_channel, *args, **kwargs)

    async def get_compliance_report(self):
        if self.certification_handler.signed_certificate is None:
            # This state shouldn't really happen...
            logger.info("Certificate is none. Waiting for signing to complete.")
            await wait_for_event_or_stop(
                self.certification_handler._signing_complete_event,
                self._stop_event,
                description="Report Signing Complete Event",
            )

        return self.certification_handler.signed_certificate


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
