from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, HTTPException
import logging
import logging.config
from fastapi import UploadFile, WebSocket
from pydantic import BaseModel
from testsuites.certificate.certificate import ComplianceReport
from testsuites.server_websocket_envelope_channel import (
    ServerWebsocketConnectionChannel,
)

from testsuites.certificate.signature import (
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

SERVER_KEY_PATH = os.environ.get("SERVER_KEY_PATH", "./server_key.pem")
KEYS_STORAGE_PATH = os.environ.get("KEYS_STORAGE_PATH", "./keys.json")


signer: ServerReportSigner | None = None
public_key_repository: KeyRepository | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global signer
    global public_key_repository

    # Used to sign and verify things with the server's public key.
    logger.info(f"Loading Server Key from `{SERVER_KEY_PATH}`")
    signer = ServerReportSigner(SERVER_KEY_PATH)

    # The place where the public keys for the organisations are stored.
    # Creates a relationship between a given organisation and their public key.
    # This can be changed to a different storage later if necessary.
    logger.info(f"Client Keys File at `{KEYS_STORAGE_PATH}`")
    public_key_repository = TextFileKeyRepository(KEYS_STORAGE_PATH)

    yield


app = FastAPI(lifespan=lifespan)


# This is the certification websocket endpoint.
# The client S2 Self Cert instances should connect to this to perform remote testing and certification.
# Once done the client will have a double signed testing certificate.
@app.websocket("/certification")
async def connect_tester(websocket: WebSocket):
    global signer
    global public_key_repository
    if signer is None or public_key_repository is None:
        logger.error("Signer and Key Repository not loaded...")
        await websocket.close()
        return

    await websocket.accept()

    # The wrapper around the FastAPI websocket for a consistent API with the python WebSockets package
    connection = FastAPIWebSocketAdapter(websocket)

    # The communication channel used to send and receive messages to the client via the above connection.
    server_channel = ServerWebsocketConnectionChannel(connection)

    certifier = ServerSideCertificationHandler(
        key_repository=public_key_repository, signer=signer
    )

    # The central part! This is what coordinated the execution and the test suit and certification.
    executor = ServerSideCertificationExecutor(certifier)

    await executor.run(server_channel)

    # Once the executor returns the testing and certification is done. Any cleanup should happen here.

    logger.info("Disconnected WebSocket.")


class CertificateStatusResponse(BaseModel):
    valid: bool


@app.post("/certificate/verify")
async def verify_certificate(file: UploadFile) -> CertificateStatusResponse:
    """
    Used to verify a double signed certificate that was produced by the certification websocket endpoint.

    Checks:
    - server signature is valid
    - client id is present in the key repository
    - client signature valid with key from specified client id

    Args:
        file (UploadFile): The YAML file containing the certificate.

    Returns:
        Status Respon: _description_
    """

    global signer
    global public_key_repository

    if signer is None or public_key_repository is None:
        logger.error("Signer and Key Repository not loaded...")
        raise HTTPException(status_code=500, detail="Configuration issue on server.")

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

        raise HTTPException(
            status_code=400, detail="Signature client id must be provided."
        )

    public_key_encoded_str = public_key_repository.get_key(
        certificate.signature.client_id
    )

    if public_key_encoded_str is None:
        raise HTTPException(
            status_code=400, detail="No organisation exists with that client_id."
        )

    # Decode the public key from string to bytes
    public_key_pem_str = CertificationEncoder.decode(public_key_encoded_str)

    public_key = signer.load_public_key_from_pem(public_key_pem_str.decode("utf-8"))

    result = signer.verify_double_signed(
        certificate, certificate.signature.client_id, public_key
    )

    return CertificateStatusResponse(valid=result)


@app.get("/healthcheck")
def healthcheck() -> dict[str, str]:
    return {"status": "OK"}
