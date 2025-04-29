import asyncio
import logging
import signal

from connection import Connection
from orchestrator import IntegrationTestOrchestrator
from websockets.asyncio.connection import Connection as WSConnection
from websockets.asyncio.server import serve as ws_serve

logger = logging.getLogger(__name__)


class S2Server:
    # Receives incoming S2 Resource Manager WebSocket Connections
    orchestrator: IntegrationTestOrchestrator

    _exit_event: asyncio.Event

    def __init__(self, host, port, orchestrator: IntegrationTestOrchestrator):
        self._host = host
        self._port = port
        self._exit_event = asyncio.Event()

        self.orchestrator = orchestrator

    async def handle_incoming_connection(self, websocket: WSConnection):
        """
        On WS connect it creates the connection instance and adds it to the Orchestrator.
        If the orchestrator already has a connection then it discards the new connection.
        This system is only meant to handle one connected device.
        """
        if not self.orchestrator.is_running():
            logger.info("Connection to RM opened.")
            connection = Connection(websocket)
            await self.orchestrator.run(connection)

            logger.info("Connection closed.")

            self.stop()
        else:
            logger.warning("This application only accepts one connection.")
            await websocket.close()

    def stop(self):
        logger.info("Stopping server...")
        self._exit_event.set()

    async def start(self):
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: self.stop())

        async with ws_serve(
            self.handle_incoming_connection, self._host, self._port
        ) as ws_server:
            logger.info(f"Websocket server started at ws://{self._host}:{self._port}")
            logger.info("Waiting for RM connection...")
            await self._exit_event.wait()
            logger.info(f"Server stopping.")

        self.orchestrator.stop()
        logger.info(f"Server stop.")
