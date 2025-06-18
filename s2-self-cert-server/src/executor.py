from importlib.metadata import version
import json
from typing import Optional
import asyncio
from connectivity.connection_adapter import ConnectionAdapter
from testsuites.certification_executor import AbstractCertificationExecutor
from connectivity.config import Config
from connectivity.s2_channel import S2Channel
from testsuites.test_executor import IntegrationTestExecutor, create_test_executor
from testsuites.certificate.certificate import ComplianceReport, Signature

from testsuites.envelope_models import (
    ClientInfoControlMessage,
    LogMessage,
    ServerMessageEnvelope,
    ControlMessage,
    ConfigControlMessage,
)
from testsuites.test_logger import (
    ServerTestLogger,
)
from connectivity.channel import Channel
from testsuites.util import wait_for_event_or_stop

import logging

from .certifier import ServerSideCertificationHandler

logger = logging.getLogger(__name__)


class MessageQueueConnectionAdapter(ConnectionAdapter):
    """This is the connection adapter that is passed to the integration test executor.
    It is designed to mimic a regular connection adapter using a websocket but is actually
    receiving S2 messages after they are received in an envelope from the client.
    """

    incoming_queue: asyncio.Queue
    outgoing_queue: asyncio.Queue

    def __init__(self) -> None:
        self.incoming_queue = asyncio.Queue()
        self.outgoing_queue = asyncio.Queue()

    async def receive(self) -> str:
        return await self.incoming_queue.get()

    async def send(self, message: str):
        return await self.outgoing_queue.put(message)

    async def get_next_outgoing(self) -> str:
        return await self.outgoing_queue.get()

    async def put_incoming(self, message: str):
        return await self.incoming_queue.put(message)

    @property
    async def open(self) -> bool:
        return True

    async def close(self, *args, **kwargs):
        pass


class MockChannel(Channel[str, str]):
    """
    This channel writes messages sent to the `MessageQueueConnectionAdapter`.
    For it's current purpose it should only receive JSON serialized S2 messages.
    """

    connection: MessageQueueConnectionAdapter

    async def send(self, message: str):
        """Writes a message to the incoming queue of the connection adapter."""
        await self.connection.put_incoming(message)

    async def receive(self) -> str:
        """Pops a message off the outgoing message queue of the connection adapter."""
        return await self.connection.get_next_outgoing()


class ServerSideCertificationExecutor(AbstractCertificationExecutor):
    s2_connection_adapter: ConnectionAdapter
    config: Config

    _config_received_event: asyncio.Event
    _client_info_received_event: asyncio.Event

    # This executes the tests. Needs to be run on it's own task. Receives and sends messages via the s2_connection_adapter
    test_executor: IntegrationTestExecutor

    # All certification messages are passed to this handler.
    certification_handler: ServerSideCertificationHandler

    report: ComplianceReport

    def __init__(self, certification_handler):
        super().__init__(certification_handler)

        self._config_received_event = asyncio.Event()
        self._client_info_received_event = asyncio.Event()

        self.add_handler(ConfigControlMessage, self.handle_config_message)
        self.add_handler(ClientInfoControlMessage, self.handle_client_info)

    async def handle_config_message(self, message: ConfigControlMessage):
        self.config = message.config
        self._config_received_event.set()

    async def handle_client_info(self, message: ClientInfoControlMessage):
        """This message contains information about the client software, such as package versions to be checked. 
        Can be expanded in future to include additional checks.
        """

        connectivity_version = version("connectivity")
        testsuites_version = version("test-suites")

        client_info = message.client_info

        if connectivity_version != client_info.connectivity_version:
            self.test_logger.error(
                message="Client & Server have mismatched version of package 'connectivity'. Exiting...",
                # details=f"Expected version {connectivity_version} for package 'connectivity' but received {client_info.connectivity_version}.",
            )

        if testsuites_version != client_info.testsuites_version:
            self.test_logger.error(
                message="Client & Server have mismatched version of package 'test-suites'. Exiting...",
                # details=f"Expected version {testsuites_version} for package 'test-suites' but received {client_info.testsuites_version}.",
            )

        self._client_info_received_event.set()

    async def handle_control_message(self, message: ControlMessage):
        await self.handle_message(message)

    async def handle_log_message(self, message: LogMessage):
        raise ValueError("Log message cannot be sent to the server!")

    async def main_loop(self):

        # Wait until the config is received before setting anything up.
        await wait_for_event_or_stop(self._config_received_event, self._stop_event, description="Config Received event.")

        self.report = ComplianceReport(device=self.config.device_details)

        # Use the standard setup method for the executor. This is the same one used on the client.
        # Guarantees that the testing is as close to identical as possible.
        self.test_executor = create_test_executor(self.config, self.test_logger)

        # Setup the S2Channel which the executor uses. We are giving it a message queue conn. adapter
        # so that we can write messages to it
        s2_channel = S2Channel(self.s2_connection_adapter)

        try:
            await self.test_executor.run(s2_channel)
        except:
            logger.exception("Error in test executor.")

        logger.info("Test suite complete!")

        report = await self.get_compliance_report()

        logger.info("Starting signing process...")
        if report is not None and self.certification_handler is not None:
            report = await self.certification_handler.begin_signing_process(
                report, self.server_channel
            )

            await wait_for_event_or_stop(
                self.certification_handler._certificate_signing_complete,
                self._stop_event,
            )

            logger.info("Report sent. Exiting Main Loop.")
        else:
            logger.error("Report is None. Cannot send. Exiting Main Loop...")

        await self.stop()

    async def run(
        self,
        server_channel: Optional[Channel[ServerMessageEnvelope, str]],
        *args,
        **kwargs,
    ):
        self._config_received_event.clear()
        self._client_info_received_event.clear()

        if server_channel is not None:
            self.test_logger = ServerTestLogger(server_channel)
        else:
            raise ValueError("Server Channel is not set.")

        self.s2_connection_adapter = MessageQueueConnectionAdapter()
        s2_channel_mock = MockChannel(self.s2_connection_adapter)
        return await super().run(s2_channel_mock, server_channel, *args, **kwargs)

    async def get_compliance_report(self):
        return await self.test_executor.get_compliance_report()
