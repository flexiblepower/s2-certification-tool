import abc
import asyncio
import base64
import os
from typing import Optional
from testsuites.certificate.certificate import ComplianceReport, Signature
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.exceptions import InvalidSignature
from testsuites.message_handlers import CertificationMessageHandler
import yaml
from connectivity.channel import Channel
from testsuites.envelope_models import (
    ServerMessageEnvelope,
    CertificationEnvelope,
    CertificationMessageType,
    KeyRegistrationRequestMessage,
    ChallengeMessage,
    ChallengeProofMessage,
    ChallengeStatusMessage,
    CertificationMessage,
    parse_certification_message,
)
from testsuites.certificate.signature import (
    SimpleCertifier,
    ReportSigner,
    CertificationEncoder,
)


import logging

logger = logging.getLogger(__name__)


class KeyRepository(abc.ABC):

    @abc.abstractmethod
    def store_key(self, client_id: str, public_key: str):
        pass


class TextFileKeyRepository(KeyRepository):
    def store_key(self, client_id: str, public_key: str):

        logger.info("Storing Key for client %s", client_id)


class ServerSideCertificationHandler(CertificationMessageHandler):

    _challenge_sent_event: asyncio.Event
    _challenge_complete_event: asyncio.Event

    client_id: str
    challenge_bytes: bytes
    challenge_status: Optional[bool] = None

    signer: SimpleCertifier
    key_repository: KeyRepository

    public_key_pem: str

    def __init__(self, signer: SimpleCertifier, key_repository: KeyRepository):
        super().__init__()

        self.signer = signer
        self.key_repository = key_repository

        self._challenge_sent_event = asyncio.Event()
        self._challenge_complete_event = asyncio.Event()

    def generate_challenge(self) -> bytes:
        challenge_bytes = os.urandom(32)
        return challenge_bytes

    async def handle_key_registration_request(
        self,
        message: KeyRegistrationRequestMessage,
        channel: Channel[ServerMessageEnvelope, str],
    ):
        self.client_id = message.client_id
        self.public_key_pem = message.public_key

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
        try:
            # Load the client's public key
            client_public_key = self.signer.load_public_key_from_pem(
                self.public_key_pem
            )

            # Convert signature from base64 string back to bytes
            signature_bytes = CertificationEncoder.decode(message.signature)

            # Verify the signature using the client's public key
            result = self.signer.verify_bytes(
                signature_bytes, self.challenge_bytes, client_public_key
            )

            if result:
                response_message = "Challenge Successful"
                self.key_repository.store_key(self.client_id, self.public_key_pem)
            else:
                response_message = "Signature Failed"

        except Exception as e:
            result = False
            response_message = f"Verification error: {str(e)}"

        envelope = CertificationEnvelope(
            message=ChallengeStatusMessage(success=result, message=response_message)
        )
        self.challenge_status = result

        await channel.send(envelope)

        self._challenge_complete_event.set()
