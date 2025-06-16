from importlib.metadata import version
from typing import Optional
from fastapi import FastAPI, Response
import asyncio
from enum import Enum
import json
import logging
import logging.config
from connectivity.connection_adapter import ConnectionAdapter
from fastapi import UploadFile, WebSocket
from testsuites.certification_executor import AbstractCertificationExecutor
from connectivity.config import Config
from testsuites.server_websocket_envelope_channel import (
    ServerWebsocketConnectionChannel,
)

from testsuites.certificate.signature import SimpleCertifier
from .certifier import (
    KeyRepository,
    ServerSideCertificationHandler,
    TextFileKeyRepository,
)
from .executor import ServerSideCertificationExecutor


from .log import LOGGING_CONFIG
from .ws_adapter import FastAPIWebSocketAdapter


logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

app = FastAPI()

# Used to sign and verify things with the server's public key.
signer = SimpleCertifier("./server_key.pem")

# The place where the public keys for the organisations are stored.
# Creates a relationship between a given organisation and their public key.
public_key_repository: KeyRepository = TextFileKeyRepository()


@app.post("/certificate/verify")
def verify_certificate(file: UploadFile):
    # TODO: Implement verification
    if file:
        return {"valid": True}
    else:
        return {"valid": False}


@app.get("/healthcheck")
def healthcheck() -> dict[str, str]:
    return {"status": "OK"}


@app.websocket("/")
async def connect_tester(websocket: WebSocket):
    await websocket.accept()
    # The wrapper around the FastAPI websocket for consistency and reusability
    connection = FastAPIWebSocketAdapter(websocket)

    # The communication channel used to send and receive messages to the client via the above connection.
    server_channel = ServerWebsocketConnectionChannel(connection)

    certifier = ServerSideCertificationHandler(
        key_repository=public_key_repository, signer=signer
    )

    # The central part! This is what coordinated the execution and the test suit and certification.
    executor = ServerSideCertificationExecutor(certifier)

    await executor.run(server_channel)

    logger.info("Disconnected WebSocket.")
