import asyncio
from enum import Enum
import json
import logging
import logging.config
from typing import Callable, Dict, Optional
from fastapi import UploadFile, WebSocket
from fastapi import WebSocketDisconnect

from fastapi import FastAPI

from .log import LOGGING_CONFIG
from s2python.message import S2Message
from testsuites.server_models import (
    ConfigControlMessage,
    ControlMessageType,
    ServerMessageEnvelope,
    ControlMessage,
    ControlMessageEnvelope,
    MessageEnvelopeTypeEnum,
    S2MessageEnvelope,
    ServerMessageValidationException,
)
from testsuites.orchestrator import ServerOrchestrator
from testsuites.connection import ServerConnection
from .rm_connection import ServerRMConnection
from testsuites.config import Config


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


class WebSocketAdapter:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket

    async def send(self, message: str):
        await self.websocket.send_text(message)

    async def recv(self):
        try:
            msg = await self.websocket.receive_text()
            return msg
        except WebSocketDisconnect:
            logger.exception("WebSocket disconnected.")
            return None


class CertificationServerOrchestrator(ServerOrchestrator):
    connection: ServerRMConnection

    async def handle_control_message(message):
        logger.info("Control Message: %s", message)

    async def main_loop(self):
        pass


@app.websocket("/ws")
async def connect_tester(websocket: WebSocket):
    await websocket.accept()
    wrapper = WebSocketAdapter(websocket)
    server = CertificationServerOrchestrator()
    client_connection = ServerConnection(wrapper)
    # client_connection = StarlettWebsocketServerConnection(websocket)
    connection = ServerRMConnection(client_connection)

    await server.run(connection, client_connection)

    # await websocket.close()
