import logging
from enum import Enum
from typing import Union, Dict, Type
from pydantic import BaseModel

from testsuites.certificate.certificate import ComplianceReport

logger = logging.getLogger(__name__)


class CertificationMessageType(str, Enum):
    # Client sends public key for registration/enrollment
    KEY_REGISTRATION_REQUEST = "KEY_REGISTRATION_REQUEST"
    # Server sends random data for the client to sign (proof of possession)
    CHALLENGE = "CHALLENGE"
    # Client sends the signed challenge back to the server
    CHALLENGE_PROOF = "CHALLENGE_PROOF"
    # Server sends the result of the challenge verification
    CHALLENGE_STATUS = "CHALLENGE_STATUS"
    # Server sends certificate to client so they can sign it with their key
    RAW_CERTIFICATE = "RAW_CERTIFICATE"
    # Client signs the report and sends the signature
    CLIENT_SIGNED_CERTIFICATE = "CLIENT_SIGNED_CERTIFICATE"
    # Server verifies that the certificate sent is with the same key that was challenged
    # If valid then the server signs the certificate as well.
    DOUBLE_SIGNED_CERTIFICATE = "DOUBLE_SIGNED_CERTIFICATE"

    STATUS_RESPONSE = "STATUS_RESPONSE"


class KeyRegistrationRequestMessage(BaseModel):
    message_type: CertificationMessageType = (
        CertificationMessageType.KEY_REGISTRATION_REQUEST
    )
    public_key: str  # PEM-encoded public key
    client_id: str  # Identifier for the client


class ChallengeMessage(BaseModel):
    message_type: CertificationMessageType = CertificationMessageType.CHALLENGE
    challenge: str  # Base64-encoded random challenge data


class ChallengeProofMessage(BaseModel):
    message_type: CertificationMessageType = CertificationMessageType.CHALLENGE_PROOF
    signature: str  # Base64-encoded signature of the challenge


class RawCertificateMessage(BaseModel):
    message_type: CertificationMessageType = CertificationMessageType.RAW_CERTIFICATE
    certificate: ComplianceReport


class ClientSignedCertificateMessage(BaseModel):
    message_type: CertificationMessageType = (
        CertificationMessageType.CLIENT_SIGNED_CERTIFICATE
    )
    certificate: ComplianceReport


class DoubleSignedCertificateMessage(BaseModel):
    message_type: CertificationMessageType = (
        CertificationMessageType.DOUBLE_SIGNED_CERTIFICATE
    )
    certificate: ComplianceReport


class StatusResponseEnum(str, Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class SignatureStatusResponseCertificateMessage(BaseModel):
    message_type: CertificationMessageType = (
        CertificationMessageType.STATUS_RESPONSE
    )
    status: StatusResponseEnum
    message: str
    # The type of message which this is a response for
    response_message_type: CertificationMessageType


CertificationMessage = Union[
    KeyRegistrationRequestMessage,
    ChallengeMessage,
    ChallengeProofMessage,
    RawCertificateMessage,
    ClientSignedCertificateMessage,
    DoubleSignedCertificateMessage,
    SignatureStatusResponseCertificateMessage,
]

certification_types_dict: Dict[CertificationMessageType, Type[CertificationMessage]] = {  # type: ignore
    CertificationMessageType.KEY_REGISTRATION_REQUEST: KeyRegistrationRequestMessage,
    CertificationMessageType.CHALLENGE: ChallengeMessage,
    CertificationMessageType.CHALLENGE_PROOF: ChallengeProofMessage,
    CertificationMessageType.RAW_CERTIFICATE: RawCertificateMessage,
    CertificationMessageType.CLIENT_SIGNED_CERTIFICATE: ClientSignedCertificateMessage,
    CertificationMessageType.DOUBLE_SIGNED_CERTIFICATE: DoubleSignedCertificateMessage,
    CertificationMessageType.STATUS_RESPONSE: SignatureStatusResponseCertificateMessage,
}

class SignatureException(Exception):
    pass


def parse_certification_message(message: dict) -> CertificationMessage:  # type: ignore
    msg_type: CertificationMessageType = CertificationMessageType[
        message["message_type"]
    ]

    try:
        message_class = certification_types_dict[msg_type]
    except KeyError:
        logger.error("Invalid message type %s", msg_type)
        raise

    return message_class.model_validate(message)
