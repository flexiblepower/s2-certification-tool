from enum import Enum
import json
from typing import Type, Union
from pydantic import BaseModel

from connectivity.config import Config


class ServerMessageValidationException(Exception):
    pass


class MessageEnvelopeTypeEnum(str, Enum):
    CONTROL = "CONTROL"
    S2 = "S2"
    LOG = "LOG"


class ControlMessageType(str, Enum):
    CONFIG = "CONFIG"
    CERTIFICATE = "CERTIFICATE"


class LogMessage(BaseModel):
    level: str
    content: str


class ConfigControlMessage(BaseModel):
    message_type: ControlMessageType = ControlMessageType.CONFIG
    config: Config


ControlMessage = Union[ConfigControlMessage]


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

envelope_types_dict = {
    MessageEnvelopeTypeEnum.CONTROL: ControlMessageEnvelope,
    MessageEnvelopeTypeEnum.S2: S2MessageEnvelope,
    MessageEnvelopeTypeEnum.LOG: LogMessageEnvelope,
}


def parse_envelope(str_msg: str) -> ServerMessageEnvelope:
    msg_dict = json.loads(str_msg)

    try:
        msg_type = MessageEnvelopeTypeEnum[msg_dict["message_type"]]
        envelope_type: Type[ServerMessageEnvelope] = envelope_types_dict[msg_type]
    except KeyError:
        raise ValueError("Invalid Message Envelope Type.")

    return envelope_type.model_validate_json(str_msg)
