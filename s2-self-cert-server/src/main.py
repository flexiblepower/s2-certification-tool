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
from connectivity.s2_channel import S2Channel
from testsuites.test_executor import IntegrationTestExecutor, create_test_executor
from testsuites.certificate.certificate import ComplianceReport
from testsuites.test_suite.test_suite import AbstractTestLogger, TestLoggerLevel


from connectivity.channel import Channel

from .certifier import MockCertifier
from .executor import ServerSideCertificationExecutor


from .log import LOGGING_CONFIG
from .ws_adapter import FastAPIWebSocketAdapter


logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

app = FastAPI()

certifier_class = MockCertifier


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
    
    certifier = certifier_class()

    # The central part! This is what coordinated the execution and the test suit and certification.
    executor = ServerSideCertificationExecutor(certifier)

    await executor.run(server_channel)

    logger.info("Disconnected WebSocket.")
