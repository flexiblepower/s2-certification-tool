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


class ClientSideCertifier(CertificationMessageHandler):

    _challenge_request_sent_event: asyncio.Event
    _challenge_proof_sent_event: asyncio.Event
    _challenge_complete_event: asyncio.Event

    client_id: str
    challenge_status: Optional[bool] = None

    def __init__(self, client_id: str, signer: SimpleCertifier):
        super().__init__()

        self.signer = signer
        self.client_id = client_id

        self._challenge_request_sent_event = asyncio.Event()
        self._challenge_proof_sent_event = asyncio.Event()
        self._challenge_complete_event = asyncio.Event()

    async def send_key_registration_request(
        self, channel: Channel[ServerMessageEnvelope, str]
    ):
        logger.info("Public Key: %s", self.signer.get_public_key())

        pub_key_bytes = self.signer.get_serialized_public_key()

        envelope = CertificationEnvelope(
            message=KeyRegistrationRequestMessage(
                public_key=CertificationEncoder.encode(pub_key_bytes),
                client_id=self.client_id,
            )
        )
        await channel.send(envelope)
        self._challenge_request_sent_event.set()

    async def handle_challenge_message(
        self, message: ChallengeMessage, channel: Channel[ServerMessageEnvelope, str]
    ):
        challenge_bytes = base64.b64decode(message.challenge)

        signature_bytes = self.signer.sign_bytes(challenge_bytes)

        signature = base64.b64encode(signature_bytes)

        envelope = CertificationEnvelope(
            message=ChallengeProofMessage(signature=signature)
        )

        await channel.send(envelope)

        self._challenge_proof_sent_event.set()

    def handle_challenge_status(
        self,
        message: ChallengeStatusMessage,
        channel: Channel[ServerMessageEnvelope, str],
    ):
        self.challenge_status = message.success
        self._challenge_complete_event.set()
