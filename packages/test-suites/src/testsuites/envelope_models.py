from enum import Enum
import json
from typing import Dict, Literal, Optional, Type, Union
from pydantic import BaseModel, ValidationError

from connectivity.config import Config

from testsuites.certificate.certificate import ComplianceReport

import logging

logger = logging.getLogger(__name__)


class ServerMessageValidationException(Exception):
    pass


class MessageEnvelopeTypeEnum(str, Enum):
    CONTROL = "CONTROL"
    S2 = "S2"
    LOG = "LOG"


class ControlMessageType(str, Enum):
    CLIENT_INFO = "CLIENT_INFO"
    CONFIG = "CONFIG"
    REPORT = "REPORT"


class LogMessage(BaseModel):
    level: Literal["SUCCESS", "SOFT_ERROR", "ERROR", "INFO", "DEBUG"]
    message: str
    details: Optional[str] = None
    ident: int = 2
    logger: Literal["test", "stdout"] = "stdout"


class ClientInfo(BaseModel):
    # The version of the `connectivity` package that the client is using
    connectivity_version: str
    # The version of the `test-suites` package that the client is using
    testsuites_version: str


class ClientInfoControlMessage(BaseModel):
    message_type: ControlMessageType = ControlMessageType.CLIENT_INFO
    client_info: ClientInfo


class ConfigControlMessage(BaseModel):
    message_type: ControlMessageType = ControlMessageType.CONFIG
    config: Config


class ReportControlMessage(BaseModel):
    message_type: ControlMessageType = ControlMessageType.REPORT
    report: ComplianceReport


ControlMessage = Union[
    ConfigControlMessage, ClientInfoControlMessage, ReportControlMessage
]


class BaseEnvelope(BaseModel):
    message_type: MessageEnvelopeTypeEnum


class ControlMessageEnvelope(BaseModel):
    message_type: MessageEnvelopeTypeEnum = MessageEnvelopeTypeEnum.CONTROL
    message: ControlMessage


class LogMessageEnvelope(BaseModel):
    message_type: MessageEnvelopeTypeEnum = MessageEnvelopeTypeEnum.LOG
    message: LogMessage


class S2MessageEnvelope(BaseModel):
    message_type: MessageEnvelopeTypeEnum = MessageEnvelopeTypeEnum.S2
    # keep it as a dict so that the orchestrator can do the parsing and catch the errors as part of the testing.
    message: str


ServerMessageEnvelope = Union[
    ControlMessageEnvelope, LogMessageEnvelope, S2MessageEnvelope
]

control_types_dict: Dict[ControlMessageType, Type[ControlMessage]] = {
    ControlMessageType.CONFIG: ConfigControlMessage,
    ControlMessageType.REPORT: ReportControlMessage,
    ControlMessageType.CLIENT_INFO: ClientInfoControlMessage,
}

envelope_types_dict: Dict[MessageEnvelopeTypeEnum, Type[ServerMessageEnvelope]] = {
    MessageEnvelopeTypeEnum.CONTROL: ControlMessageEnvelope,
    MessageEnvelopeTypeEnum.S2: S2MessageEnvelope,
    MessageEnvelopeTypeEnum.LOG: LogMessageEnvelope,
}


def parse_control_message(message: dict) -> ControlMessage:
    msg_type: ControlMessageType = ControlMessageType[message["message_type"]]

    try:
        message_class = control_types_dict[msg_type]
    except KeyError as e:
        logger.error("Invalid message type %s", msg_type)
        raise

    return message_class.model_validate(message)


def parse_envelope(envelope_json: str) -> ServerMessageEnvelope:

    try:
        raw_envelope: dict = json.loads(envelope_json)

        msg_type = MessageEnvelopeTypeEnum[raw_envelope["message_type"]]

        envelope_class: Type[ServerMessageEnvelope] = envelope_types_dict[msg_type]

        if msg_type == MessageEnvelopeTypeEnum.CONTROL:
            logger.info("Parsing control message.")
            envelope = ControlMessageEnvelope(
                message=parse_control_message(raw_envelope["message"])
            )
            logger.info("Control message parsed.")
            return envelope
        else:
            return envelope_class.model_validate_json(envelope_json)
    except json.JSONDecodeError:
        raise ValueError("JSON decode exception.")
    except ValidationError:
        raise ValueError("Message Validation Error")
    except KeyError:
        raise ValueError("Invalid Message Envelope Type.")
