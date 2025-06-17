from importlib.metadata import version
from typing import Optional
from fastapi import FastAPI, HTTPException, Response
import asyncio
from enum import Enum
import json
import logging
import logging.config
from connectivity.connection_adapter import ConnectionAdapter
from fastapi import UploadFile, WebSocket
from testsuites.certificate.certificate import ComplianceReport
from testsuites.certification_executor import AbstractCertificationExecutor
from connectivity.config import Config
from testsuites.server_websocket_envelope_channel import (
    ServerWebsocketConnectionChannel,
)

from testsuites.certificate.signature import (
    SimpleCertifier,
    ServerReportSigner,
    CertificationEncoder,
)
import yaml
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
signer = ServerReportSigner("./server_key.pem")

# The place where the public keys for the organisations are stored.
# Creates a relationship between a given organisation and their public key.
public_key_repository: KeyRepository = TextFileKeyRepository("./keys.txt")


@app.post("/certificate/verify")
async def verify_certificate(file: UploadFile):
    # if file:

    #     yaml_data = yaml.load
    #     return {"valid": True}
    # else:
    #     return {"valid": False}

    # Check valid content
    if file.content_type not in ("text/yaml", "application/x-yaml", "text/x-yaml"):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Please upload a YAML file."
        )

    # Read the file contents
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="Unable to decode file as UTF-8 text."
        )

    # Parse YAML
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML parsing error: {e}")

    certificate = ComplianceReport.model_validate(data)

    if certificate.signature.client_id is None:

        return HTTPException(
            status_code=400, detail="Signature client id must be provided."
        )

    public_key_encoded_str = public_key_repository.get_key(
        certificate.signature.client_id
    )

    if public_key_encoded_str is None:
        raise HTTPException(
            status_code=400, detail="No organisation exists with that client_id."
        )

    public_key_pem_str = CertificationEncoder.decode(public_key_encoded_str)

    public_key = signer.load_public_key_from_pem(public_key_pem_str.decode("utf-8"))

    result = signer.verify_double_signed(
        certificate, certificate.signature.client_id, public_key
    )

    return {"valid": result}


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
