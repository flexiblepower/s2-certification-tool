from enum import Enum
from typing import Union
from pydantic import BaseModel

from s2python.message import S2Message
from s2testing.config import Config


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


class ControlMessageEnvelope(BaseModel):
    message_type: MessageEnvelopeTypeEnum = MessageEnvelopeTypeEnum.CONTROL
    message: ControlMessage


class LogMessageEnvelope(BaseModel):
    message_type: MessageEnvelopeTypeEnum = MessageEnvelopeTypeEnum.LOG
    message: LogMessage


class S2MessageEnvelope(BaseModel):
    message_type: MessageEnvelopeTypeEnum = MessageEnvelopeTypeEnum.S2
    # keep it as a dict so that the orchestrator can do the parsing and catch the errors as part of the testing.
    message: dict


ServerMessageEnvelope = Union[ControlMessageEnvelope, LogMessageEnvelope, S2MessageEnvelope]
