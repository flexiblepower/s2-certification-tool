import abc
import asyncio
import base64
import json
import os
import threading
from typing import Optional, Union
from fastapi import Path
from testsuites.certificate.certificate import ComplianceReport
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.types import PublicKeyTypes
from testsuites.message_handlers import CertificationMessageHandler
import yaml
from connectivity.channel import Channel
from testsuites.util import wait_for_event_or_stop
from testsuites.envelope_models import (
    ServerMessageEnvelope,
    CertificationEnvelope,
    CertificationMessageType,
    KeyRegistrationRequestMessage,
    ChallengeMessage,
    ChallengeProofMessage,
    RawCertificateMessage,
    ClientSignedCertificateMessage,
    DoubleSignedCertificateMessage,
    SignatureStatusResponseCertificateMessage,
    StatusResponseEnum,
    SignatureException,
    CertificationMessage,
    parse_certification_message,
)
from testsuites.certificate.signature import (
    SimpleCertifier,
    ReportSigner,
    CertificationEncoder,
    ServerReportSigner,
)
from pathlib import Path

import logging

logger = logging.getLogger(__name__)


class KeyRepository(abc.ABC):
    """Abstract key repository that is used to store the public keys registered by organisations who wish to certify their S2 Implementations."""

    @abc.abstractmethod
    def store_key(self, client_id: str, public_key: str):
        """
        Store a public key and it's associated client_id
        """

    @abc.abstractmethod
    def get_key(self, client_id: str) -> Optional[str]:
        """
        Retrieve the public key for the given client_id.
        Returns None if no key is stored for that client.
        """


class TextFileKeyRepository(KeyRepository):
    """
    A KeyRepository that persists client public keys in a JSON text file.
    """

    def __init__(self, file_path: Union[str, Path]):
        self.file_path = Path(file_path)
        self._lock = threading.Lock()

        # Ensure the file exists and contains at least an empty JSON object
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text("{}", encoding="utf-8")

    def store_key(self, client_id: str, public_key: str):
        logger.info("Storing key for client %s", client_id)

        with self._lock:
            # Read existing data
            # TODO: This could be problematic if the file gets large.
            try:
                content = self.file_path.read_text(encoding="utf-8")
                data = json.loads(content)
            except (json.JSONDecodeError, OSError):
                data = {}

            # Update the key for this client
            data[client_id] = public_key

            # Atomically write back the full map
            tmp_path = self.file_path.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as tf:
                json.dump(data, tf, indent=2)
                tf.flush()
            tmp_path.replace(self.file_path)

    def get_key(self, client_id: str) -> Optional[str]:
        """
        Retrieve the public key for the given client_id.
        Returns None if no key is stored for that client.
        """
        logger.info("Retrieving key for client %s", client_id)

        with self._lock:
            try:
                content = self.file_path.read_text(encoding="utf-8")
                data = json.loads(content)
            except (json.JSONDecodeError, OSError):
                return None

            return data.get(client_id)


class ServerSideCertificationHandler(CertificationMessageHandler):

    _challenge_sent_event: asyncio.Event
    _challenge_complete_event: asyncio.Event
    _certificate_signing_complete: asyncio.Event

    client_id: str
    challenge_bytes: bytes
    challenge_status: Optional[bool] = None

    signer: ServerReportSigner
    key_repository: KeyRepository

    client_public_key: PublicKeyTypes

    previous_message: Optional[CertificationMessage] = None

    def __init__(self, signer: ServerReportSigner, key_repository: KeyRepository):
        super().__init__()

        self.signer = signer
        self.key_repository = key_repository

        self._challenge_sent_event = asyncio.Event()
        self._challenge_complete_event = asyncio.Event()

        self._certificate_signing_complete = asyncio.Event()

        self.add_handler(
            KeyRegistrationRequestMessage, self.handle_key_registration_request
        )
        self.add_handler(ChallengeProofMessage, self.handle_challenge_proof)
        self.add_handler(
            ClientSignedCertificateMessage, self.handle_client_signed_certificate
        )

    async def send_message(
        self,
        message: CertificationMessage,
        channel: Channel[ServerMessageEnvelope, str],
    ):
        await channel.send(CertificationEnvelope(message=message))
        self.previous_message = message

    def generate_challenge(self) -> bytes:
        challenge_bytes = os.urandom(32)
        return challenge_bytes

    async def handle_key_registration_request(
        self,
        message: KeyRegistrationRequestMessage,
        channel: Channel[ServerMessageEnvelope, str],
    ):
        logger.info("Handling Key Registration Request")
        self.client_id = message.client_id

        # Key is already UTF-8 Encoded.
        public_key_pem_str = CertificationEncoder.decode(message.public_key)

        self.client_public_key = self.signer.load_public_key_from_pem(
            public_key_pem_str.decode("utf-8")
        )

        self.challenge_bytes = self.generate_challenge()

        challenge_bytes_b64 = CertificationEncoder.encode(self.challenge_bytes)

        envelope = CertificationEnvelope(
            message=ChallengeMessage(challenge=challenge_bytes_b64)
        )

        await channel.send(envelope)

        self._challenge_sent_event.set()

    async def handle_challenge_proof(
        self,
        message: ChallengeProofMessage,
        channel: Channel[ServerMessageEnvelope, str],
    ):
        logger.info("Handling Challenge Proof Message")

        response_message = SignatureStatusResponseCertificateMessage(
            status=StatusResponseEnum.SUCCESS,
            message="Challenge Successful",
            response_message_type=message.message_type,
        )
        try:
            logger.info("Starting validation")

            # Convert signature from base64 string back to bytes
            signature_bytes = CertificationEncoder.decode(message.signature)

            # Verify the signature using the client's public key
            certificate_valid = self.signer.verify_bytes(
                signature_bytes, self.challenge_bytes, self.client_public_key
            )

            if certificate_valid:
                logger.info("Challenge Certificate is Valid.")
                self.key_repository.store_key(
                    self.client_id,
                    CertificationEncoder.encode(
                        self.client_public_key.public_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PublicFormat.SubjectPublicKeyInfo,
                        )
                    ),
                )
            else:
                logger.warning("Challenge Failed. Invalid Signature.")
                response_message.message = "Challenge Failed. Invalid signature."
                response_message.status = StatusResponseEnum.ERROR

        except Exception as e:
            certificate_valid = False
            logger.exception("Challenge Failed. Invalid Signature.")
            response_message.message = "Challenge Failed due to verification error."
            response_message.status = StatusResponseEnum.ERROR

        envelope = CertificationEnvelope(message=response_message)
        self.challenge_status = certificate_valid

        await channel.send(envelope)

        self._challenge_complete_event.set()

    async def begin_signing_process(
        self, report: ComplianceReport, channel: Channel[ServerMessageEnvelope, str]
    ):
        logger.info("Starting Signing Process")
        # Set the client ID to make sure it matches.
        report.signature.client_id = self.client_id
        envelope = CertificationEnvelope(
            message=RawCertificateMessage(certificate=report)
        )
        await channel.send(envelope)

    async def handle_client_signed_certificate(
        self,
        message: ClientSignedCertificateMessage,
        channel: Channel[ServerMessageEnvelope, str],
    ):
        logger.info("Handling Client Signed Certificate")
        report = message.certificate

        # Verify that the client signature is valid given the key provided at the start
        if not self.signer.verify_client_signed(
            report, self.client_id, self.client_public_key
        ):
            logger.info("Signature not valid. Sending ERROR response.")
            envelope = CertificationEnvelope(
                message=SignatureStatusResponseCertificateMessage(
                    status=StatusResponseEnum.ERROR,
                    message="Client Signature is not valid.",
                    response_message_type=CertificationMessageType.CLIENT_SIGNED_CERTIFICATE,
                )
            )
            raise SignatureException("Client Signature not valid.")

        logger.info("Signature is valid. Double Signing with server key.")
        # Sign the report with the server certificate. Client signature is included in the body - double signed
        logger.info(json.dumps(report.model_dump(), indent=2, default=str))
        report = self.signer.sign_report(report, self.client_id)

        # Send the double signed report back to the client.
        envelope = CertificationEnvelope(
            message=DoubleSignedCertificateMessage(certificate=report)
        )

        await channel.send(envelope)

        self._certificate_signing_complete.set()
