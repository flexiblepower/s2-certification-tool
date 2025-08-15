import asyncio
from typing import Optional
from testsuites.message_handlers import CertificationMessageHandler
from connectivity.channel import Channel
from testsuites.envelope_models import (
    ServerMessageEnvelope,
    CertificationEnvelope,
    CertificationMessageType,
    KeyRegistrationRequestMessage,
    ChallengeMessage,
    ChallengeProofMessage,
    RawCertificateMessage,
    ClientSignedCertificateMessage,
    StatusResponseEnum,
    DoubleSignedCertificateMessage,
    SignatureStatusResponseCertificateMessage,
    CertificationMessage,
)
from testsuites.certificate.signature import (
    CertificationEncoder,
    ClientReportSigner,
)
from testsuites.certificate.certificate import ComplianceReport

import logging

logger = logging.getLogger(__name__)


class ClientSideCertifier(CertificationMessageHandler):

    # Performs all the cryptographic signing processes
    signer: ClientReportSigner

    _challenge_request_sent_event: asyncio.Event
    _challenge_proof_sent_event: asyncio.Event
    _challenge_complete_event: asyncio.Event

    _signing_started_event: asyncio.Event
    _signing_complete_event: asyncio.Event

    signing_valid: Optional[bool] = None
    signed_certificate: Optional[ComplianceReport] = None

    client_id: str
    challenge_status: Optional[bool] = None

    previous_message: Optional[CertificationMessage] = None

    def __init__(self, client_id: str, signer: ClientReportSigner):
        super().__init__()

        self.signer = signer
        self.client_id = client_id

        self._challenge_request_sent_event = asyncio.Event()
        self._challenge_proof_sent_event = asyncio.Event()
        self._challenge_complete_event = asyncio.Event()

        self._signing_complete_event = asyncio.Event()
        self._signing_started_event = asyncio.Event()

        self.add_handler(ChallengeMessage, self.handle_challenge_message)
        self.add_handler(RawCertificateMessage, self.handle_raw_certificate_message)
        self.add_handler(
            DoubleSignedCertificateMessage,
            self.handle_double_signed_certificate_message,
        )
        self.add_handler(
            SignatureStatusResponseCertificateMessage, self.handle_status_message
        )

    async def send_message(
        self,
        message: CertificationMessage,
        channel: Channel[ServerMessageEnvelope, str],
    ):
        await channel.send(CertificationEnvelope(message=message))
        self.previous_message = message

    async def send_key_registration_request(
        self, channel: Channel[ServerMessageEnvelope, str]
    ):
        pub_key_bytes = self.signer.get_serialized_public_key()

        message = KeyRegistrationRequestMessage(
            public_key=CertificationEncoder.encode(pub_key_bytes),
            client_id=self.client_id,
        )
        await self.send_message(message, channel)
        self._challenge_request_sent_event.set()

    async def handle_challenge_message(
        self, message: ChallengeMessage, channel: Channel[ServerMessageEnvelope, str]
    ):
        challenge_bytes = CertificationEncoder.decode(message.challenge)

        signature_bytes = self.signer.sign_bytes(challenge_bytes)

        signature = CertificationEncoder.encode(signature_bytes)

        message = ChallengeProofMessage(signature=signature)
        await self.send_message(message, channel)

        self._challenge_proof_sent_event.set()

    async def handle_raw_certificate_message(
        self,
        message: RawCertificateMessage,
        channel: Channel[ServerMessageEnvelope, str],
    ):
        # Receive the unsigned report, sign it with the private key, send back to be signed by server
        # Server will check if signature valid for key provided during Challenge

        if not self._challenge_complete_event.is_set():
            raise ValueError(
                "Received raw certificate but challenge is not complete..."
            )

        certificate = self.signer.sign_report(message.certificate)

        message = ClientSignedCertificateMessage(certificate=certificate)

        await self.send_message(message, channel)

    async def handle_double_signed_certificate_message(
        self,
        message: DoubleSignedCertificateMessage,
        channel: Channel[ServerMessageEnvelope, str],
    ):
        # Receive the certificate which has been signed by both this client and the server.
        # This is just saved to a variable and can be read by an external class.

        self.signing_valid = True
        self.signed_certificate = message.certificate
        self._signing_complete_event.set()

    async def handle_status_message(
        self,
        message: SignatureStatusResponseCertificateMessage,
        channel: Channel[ServerMessageEnvelope, str],
    ):
        # Status messages are sent at the end of the Challenge and during Certification if there is a problem
        if (
            self.previous_message.message_type
            == CertificationMessageType.CHALLENGE_PROOF
            and message.response_message_type
            == CertificationMessageType.CHALLENGE_PROOF
        ):
            self.challenge_status = message.status == StatusResponseEnum.SUCCESS
            self._challenge_complete_event.set()
        elif (
            self.previous_message.message_type
            == CertificationMessageType.CLIENT_SIGNED_CERTIFICATE
            and message.response_message_type
            == CertificationMessageType.CLIENT_SIGNED_CERTIFICATE
        ):
            self.signing_valid = message.status == StatusResponseEnum.SUCCESS
            self._signing_complete_event.set()
