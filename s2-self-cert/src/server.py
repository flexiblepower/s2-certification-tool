import asyncio
import logging
import signal
from typing import Literal, Optional

from testsuites.test_executor import IntegrationTestExecutor
from websockets import connect
from websockets.asyncio.connection import Connection as WSConnection
from websockets.asyncio.server import serve as ws_serve
from ws_adapter import WebSocketConnectionAdapter
from connectivity.channel import Channel, BaseChannel
from connectivity.config import ConnectionConfig
from connectivity.s2_channel import S2Channel

from testsuites.certification_executor import AbstractCertificationExecutor

logger = logging.getLogger(__name__)


class S2WebSocketBase:
    executor: AbstractCertificationExecutor
    mode: Literal["testing", "certification"]

    config: ConnectionConfig

    _exit_event: asyncio.Event

    def __init__(
        self,
        config: ConnectionConfig,
        orchestrator: AbstractCertificationExecutor,
        mode: Literal["testing", "certification"],
        report_output_file: Optional[str] = None,
    ):
        self._exit_event = asyncio.Event()

        self.config = config
        self.mode = mode

        self.executor = orchestrator

        self.report_output_file = report_output_file

    async def start_with_connection(self, websocket: WSConnection):
        """
        On WS connect it creates the connection instance and adds it to the Orchestrator.
        If the orchestrator already has a connection then it discards the new connection.
        This system is only meant to handle one connected device.
        """
        if not self.executor.is_running():
            logger.info("Connection to RM opened.")
            connection = WebSocketConnectionAdapter(websocket)

            if self.mode == "testing":
                logger.info("Starting in test mode. All tests are run locally.")
                s2_channel = S2Channel(connection)
            else:
                logger.info(
                    "Starting in certification mode. All tests are run remotely."
                )
                s2_channel = BaseChannel(connection)

            await self.executor.run(s2_channel)

            logger.info("Exporting Compliance Report.")
            self.executor.report.export(self.report_output_file)

            logger.info("Connection closed.")

            await self.stop()
        else:
            logger.warning("This application only accepts one connection.")
            await websocket.close()


class S2WebSocketServer(S2WebSocketBase):
    # Receives incoming S2 Resource Manager WebSocket Connections
    executor: AbstractCertificationExecutor
    mode: Literal["testing", "certification"]

    _exit_event: asyncio.Event

    async def stop(self):
        logger.info("Stopping server...")
        self._exit_event.set()

    async def start(self):
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        async with ws_serve(
            self.start_with_connection, self.config.host, self.config.port
        ) as ws_server:
            logger.info(
                f"Websocket server started at ws://{self.config.host}:{self.config.port}"
            )
            logger.info("Waiting for RM connection...")
            await self._exit_event.wait()
            logger.info(f"Server stopping.")

        await self.executor.stop()
        logger.info(f"Server stop.")


class S2WebSocketClient(S2WebSocketBase):

    async def start(self):
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        logger.info(f"Connection to Websocket server at {self.config.uri}")
        async with connect(self.config.uri) as websocket:
            await self.start_with_connection(websocket)

    async def stop(self):
        logger.info("Stopping...")
        await self.executor.stop()
