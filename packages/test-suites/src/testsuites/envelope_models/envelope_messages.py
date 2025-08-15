from enum import Enum
import json
from typing import Dict, Literal, Optional, Type, Union
from pydantic import BaseModel, ValidationError

from connectivity.config import Config

from testsuites.certificate.certificate import ComplianceReport

from .control_message import ControlMessage, parse_control_message
from .certification_message import CertificationMessage, parse_certification_message

import logging

logger = logging.getLogger(__name__)


class ServerMessageValidationException(Exception):
    pass


class MessageEnvelopeTypeEnum(str, Enum):
    CONTROL = "CONTROL"
    S2 = "S2"
    LOG = "LOG"
    CERTIFICATION = "CERTIFICATION"


class LogMessage(BaseModel):
    level: Literal["SUCCESS", "SOFT_ERROR", "ERROR", "INFO", "DEBUG"]
    message: str
    details: Optional[str] = None
    ident: int = 2
    logger: Literal["test", "stdout"] = "stdout"


# ----- Envelopes -----


class BaseEnvelope(BaseModel):
    message_type: MessageEnvelopeTypeEnum


class ControlMessageEnvelope(BaseEnvelope):
    message_type: MessageEnvelopeTypeEnum = MessageEnvelopeTypeEnum.CONTROL
    message: ControlMessage  # type: ignore


class LogMessageEnvelope(BaseEnvelope):
    message_type: MessageEnvelopeTypeEnum = MessageEnvelopeTypeEnum.LOG
    message: LogMessage


class S2MessageEnvelope(BaseEnvelope):
    message_type: MessageEnvelopeTypeEnum = MessageEnvelopeTypeEnum.S2
    # keep it as a dict so that the orchestrator can do the parsing and catch the errors as part of the testing.
    message: str


class CertificationEnvelope(BaseEnvelope):
    message_type: MessageEnvelopeTypeEnum = MessageEnvelopeTypeEnum.CERTIFICATION
    message : CertificationMessage


ServerMessageEnvelope = Union[
    ControlMessageEnvelope, LogMessageEnvelope, S2MessageEnvelope, CertificationEnvelope
]


envelope_types_dict: Dict[MessageEnvelopeTypeEnum, Type[ServerMessageEnvelope]] = {
    MessageEnvelopeTypeEnum.CONTROL: ControlMessageEnvelope,
    MessageEnvelopeTypeEnum.S2: S2MessageEnvelope,
    MessageEnvelopeTypeEnum.LOG: LogMessageEnvelope,
    MessageEnvelopeTypeEnum.CERTIFICATION: CertificationEnvelope,
}


def parse_envelope(envelope_json: str) -> ServerMessageEnvelope:

    try:
        raw_envelope: dict = json.loads(envelope_json)

        msg_type = MessageEnvelopeTypeEnum[raw_envelope["message_type"]]

        envelope_class: Type[ServerMessageEnvelope] = envelope_types_dict[msg_type]

        if msg_type == MessageEnvelopeTypeEnum.CONTROL:
            envelope = ControlMessageEnvelope(
                message=parse_control_message(raw_envelope["message"])
            )
            return envelope
        elif msg_type == MessageEnvelopeTypeEnum.CERTIFICATION:
            envelope = CertificationEnvelope(
                message=parse_certification_message(raw_envelope["message"])
            )
            return envelope
        else:
            return envelope_class.model_validate_json(envelope_json)
    except json.JSONDecodeError:
        raise ValueError("JSON decode exception.")
    except ValidationError:
        raise ValueError("Message Validation Error")
    except KeyError:
        raise ValueError("Invalid Message Envelope Type.")
