from importlib.metadata import version
from typing import Optional
from fastapi import FastAPI
import asyncio
from enum import Enum
import json
import logging
import logging.config
from connectivity.connection_adapter import ConnectionAdapter
from fastapi import UploadFile, WebSocket
from fastapi import WebSocketDisconnect
from testsuites.certification_executor import AbstractCertificationExecutor
from connectivity.config import Config
from testsuites.server_websocket_envelope_channel import (
    ServerWebsocketConnectionChannel,
)
from connectivity.s2_channel import S2Channel
from testsuites.test_executor import IntegrationTestExecutor, create_test_executor


from testsuites.envelope_models import (
    ClientInfoControlMessage,
    ServerMessageEnvelope,
    S2MessageEnvelope,
    LogMessage,
    LogMessageEnvelope,
    ControlMessage,
    ConfigControlMessage,
    ReportControlMessage,
    ControlMessageEnvelope,
    ControlMessageType,
    MessageEnvelopeTypeEnum,
    BaseEnvelope,
)
from connectivity.channel import Channel


from log import LOGGING_CONFIG
from ws_adapter import FastAPIWebSocketAdapter


logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

app = FastAPI()


@app.post("/certificate/verify")
def verify_certificate(file: UploadFile):
    # TODO: Implement verification
    if file:
        return {"valid": True}
    else:
        return {"valid": False}


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
        # logger.info("S2 Message: %s", message)
        await self.connection.put_incoming(message)

    async def receive(self) -> str:
        return await self.connection.get_next_outgoing()


from testsuites.certificate.certificate import ComplianceReport


class ServerSideCertificationExecutor(AbstractCertificationExecutor):
    s2_connection_adapter: ConnectionAdapter
    config: Config

    _config_received: asyncio.Event

    test_executor: IntegrationTestExecutor

    report: ComplianceReport

    def __init__(self):
        super().__init__()

        self.add_handler(ConfigControlMessage, self.handle_config_message)

    async def handle_config_message(self, message: ConfigControlMessage):
        self.config = message.config

        self._config_received.set()

    async def handle_client_info(self, message: ClientInfoControlMessage):

        connectivity_version = version("connectivity")
        testsuites_version = version("test-suites")

        client_info = message.client_info

        if connectivity_version != client_info.connectivity_version:
            await self.send_server_log_message(
                message="Client & Server have mismatched version of package 'connectivity'. Exiting...",
                details=f"Expected version {connectivity_version} for package 'connectivity' but received {client_info.connectivity_version}.",
            )

        if testsuites_version != client_info.testsuites_version:
            await self.send_server_log_message(
                message="Client & Server have mismatched version of package 'test-suites'. Exiting...",
                details=f"Expected version {testsuites_version} for package 'test-suites' but received {client_info.testsuites_version}.",
            )

        await self.stop()

    async def handle_control_message(self, message: ControlMessage):
        logger.debug("Control Message: %s", message)
        await self.handle_message(message)

    async def send_report(self, report: ComplianceReport):
        logger.info("Sending report: %s", report)
        message = ReportControlMessage(report=report)

        await self.send_server_control_message(message)

    async def main_loop(self):

        await self._config_received.wait()

        logger.debug("Config Received.")

        self.report = ComplianceReport(device=self.config.device_details)

        self.test_executor = create_test_executor(self.config)

        s2_channel = S2Channel(self.s2_connection_adapter)

        try:
            await self.test_executor.run(s2_channel)
        except:
            logger.exception("Error in test executor.")

        logger.info("Test suite complete!")

        report = self.test_executor.report

        logger.info("Sending report")

        report.signature = "TEST SERVER SIGNATURE"

        await self.send_report(report)

        logger.info("Report sent. Exiting Main Loop.")

        await self.stop()

    async def run(
        self,
        server_channel: Optional[Channel[ServerMessageEnvelope, str]],
        *args,
        **kwargs,
    ):
        self._config_received = asyncio.Event()

        self.s2_connection_adapter = MockConnectionAdapter()
        s2_channel_mock = MockChannel(self.s2_connection_adapter)
        return await super().run(s2_channel_mock, server_channel, *args, **kwargs)


@app.websocket("/ws")
async def connect_tester(websocket: WebSocket):
    await websocket.accept()
    # The wrapper around the FastAPI websocket for consistency and reusability
    connection = FastAPIWebSocketAdapter(websocket)

    # The communication channel used to send and receive messages to the client via the above connection.
    server_channel = ServerWebsocketConnectionChannel(connection)

    # The central part! This is what coordinated the execution and the test suit and certification.
    executor = ServerSideCertificationExecutor()

    await executor.run(server_channel)

    logger.info("Disconnected WebSocket.")
