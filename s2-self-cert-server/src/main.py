import asyncio
from enum import Enum
import json
import logging
import logging.config
from typing import Callable, Dict, Optional
from fastapi import UploadFile, WebSocket

from fastapi import FastAPI

from .log import LOGGING_CONFIG
from s2python.message import S2Message
from .model import (
    ConfigControlMessage,
    ControlMessageType,
    ServerMessage,
    ControlMessage,
    ControlMessageEnvelope,
    MessageEnvelopeTypeEnum,
    S2MessageEnvelope,
    ServerMessageValidationException,
)
from .client_connection import ClientConnection
from .rm_connection import RMConnection
from s2testing.async_task_manager import AsyncTaskManager
from s2testing.config import Config


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


class ServerController:
    handlers: Dict[ControlMessageType, Callable] = {}

    config: Optional[Config] = None

    def __init__(self):
        self.handlers = {ControlMessageType.CONFIG: self.handle_config_message}

    async def handle_config_message(self, message: ConfigControlMessage):
        logger.info("Config Message: %s", message.config)
        self.config = message.config

    async def handle_message(self, message: ControlMessage):
        try:
            handler: Callable = self.handlers[message.message_type]

            await handler(message)
        except KeyError:
            logger.warning("No handler for `%s` message type.", message.message_type)


class CertificationServerManager(AsyncTaskManager):
    client_connection: ClientConnection
    rm_connection: RMConnection

    controller: Optional[ServerController] = None

    def __init__(self, websocket: WebSocket) -> None:
        super().__init__()
        self.client_connection = ClientConnection(websocket)
        self.rm_connection = RMConnection(self.client_connection)

        self.controller = ServerController()

    async def handle_s2_message(self, message: S2Message):
        await self.rm_connection.add_message_to_queue(message)

    async def process_received_messages(self):
        """AsyncIO task which pops messages off the queue and processes them using the control type."""

        if self.client_connection is None:
            raise ValueError("Connection not set.")

        logger.info("Server processing messages.")

        try:
            while not self._stop_event.is_set():
                try:
                    # Use a timeout to periodically check for cancellation
                    envelope: ServerMessage = await asyncio.wait_for(
                        self.client_connection.get_next_message(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue  # Check stop event and loop again

                if envelope.message_type == MessageEnvelopeTypeEnum.CONTROL:
                    await self.controller.handle_message(envelope.message)
                elif envelope.message_type == MessageEnvelopeTypeEnum.S2:
                    await self.handle_s2_message(envelope.message)
                else:
                    raise ValueError("Invalid message type.")

        except asyncio.CancelledError:
            logger.info("Message receiver cancelled.")
        except Exception as e:
            logger.exception("Message processor encountered an error: %s", e)
        finally:
            self.stop()

    # async def connection_receive_messages(self):
    #     pass

    async def main_loop(self):
        pass

    async def setup(self, *args, **kwargs):
        await super().setup()

        self.create_task(self.client_connection.receive_messages(), True)
        self.create_task(self.process_received_messages(), True)
        # self.create_task(self.main_loop(), True)

    async def run(self):
        self.running = True

        await self.setup()

        logger.info("Setup complete %s", self._stop_event)
        await self._stop_event.wait()
        logger.info("Cleaning up. %s", self._stop_event)

        await self.cleanup()

        self.running = False


@app.websocket("/ws")
async def connect_tester(websocket: WebSocket):
    await websocket.accept()
    server = CertificationServerManager(websocket)
    await server.run()

    await websocket.close()
