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
    ReportControlMessage,
)
from testsuites.test_logger import (
    ServerTestLogger,
)
from connectivity.channel import Channel
from testsuites.util import wait_for_event_or_stop

import logging

from .certifier import ServerSideCertificationHandler

logger = logging.getLogger(__name__)


class MockConnectionAdapter(ConnectionAdapter):

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
    connection: MockConnectionAdapter

    async def send(self, message: str):
        await self.connection.put_incoming(message)

    async def receive(self) -> str:
        return await self.connection.get_next_outgoing()


class ServerSideCertificationExecutor(AbstractCertificationExecutor):
    s2_connection_adapter: ConnectionAdapter
    config: Config

    _config_received_event: asyncio.Event
    _client_info_received_event: asyncio.Event

    test_executor: IntegrationTestExecutor
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
        logger.debug("Control Message: %s", message)
        await self.handle_message(message)

    async def send_report(self, report: ComplianceReport):
        logger.info("Sending report: %s", report)
        message = ReportControlMessage(report=report)

        await self.send_server_control_message(message)

    async def handle_log_message(self, message: LogMessage):
        raise ValueError("Log message cannot be sent to the server!")

    async def main_loop(self):

        await self._config_received_event.wait()

        logger.debug("Config Received.")

        self.report = ComplianceReport(device=self.config.device_details)

        self.test_executor = create_test_executor(self.config, self.test_logger)

        s2_channel = S2Channel(self.s2_connection_adapter)

        try:
            await self.test_executor.run(s2_channel)
        except:
            logger.exception("Error in test executor.")

        logger.info("Test suite complete!")

        report = await self.get_compliance_report()


        logger.info("Starting signing process...")
        if report is not None and self.certification_handler is not None:
            report = await self.certification_handler.begin_signing_process(report, self.server_channel)

            await wait_for_event_or_stop(
                self.certification_handler._certificate_signing_complete,
                self._stop_event,
            )

            # await self.send_report(report)

            # logger.info(
            #     "Certificate: %s",
            #     json.dumps(report.model_dump(), indent=2, default=str),
            # )

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

        self.s2_connection_adapter = MockConnectionAdapter()
        s2_channel_mock = MockChannel(self.s2_connection_adapter)
        return await super().run(s2_channel_mock, server_channel, *args, **kwargs)

    async def get_compliance_report(self):
        return await self.test_executor.get_compliance_report()
