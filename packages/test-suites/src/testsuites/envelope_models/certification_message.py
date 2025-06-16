import logging
from enum import Enum
from typing import Union, Dict, Type
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CertificationMessageType(str, Enum):
    # Client sends public key for registration/enrollment
    KEY_REGISTRATION_REQUEST = "KEY_REGISTRATION_REQUEST"
    # Server sends random data for the client to sign (proof of possession)
    CHALLENGE = "CHALLENGE"
    # Client sends the signed challenge back to the server
    CHALLENGE_PROOF = "CHALLENGE_SIGNATURE"
    # Server sends the result of the challenge verification
    CHALLENGE_STATUS = "CHALLENGE_STATUS"


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


class ChallengeStatusMessage(BaseModel):
    message_type: CertificationMessageType = CertificationMessageType.CHALLENGE_STATUS
    success: bool  # Whether the challenge verification succeeded
    message: str  # Human-readable status message


CertificationMessage = Union[
    KeyRegistrationRequestMessage,
    ChallengeMessage,
    ChallengeProofMessage,
    ChallengeStatusMessage,
]

certification_types_dict: Dict[CertificationMessageType, Type[CertificationMessage]] = {  # type: ignore
    CertificationMessageType.KEY_REGISTRATION_REQUEST: KeyRegistrationRequestMessage,
    CertificationMessageType.CHALLENGE: ChallengeMessage,
    CertificationMessageType.CHALLENGE_PROOF: ChallengeProofMessage,
    CertificationMessageType.CHALLENGE_STATUS: ChallengeStatusMessage,
}


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
