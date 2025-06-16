from enum import Enum
import json
from typing import Dict, Literal, Optional, Type, Union
from pydantic import BaseModel, ValidationError

from connectivity.config import Config

from testsuites.certificate.certificate import ComplianceReport
import logging

logger = logging.getLogger(__name__)


class ControlMessageType(str, Enum):
    CLIENT_INFO = "CLIENT_INFO"
    CONFIG = "CONFIG"
    REPORT = "REPORT"


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

control_types_dict: Dict[ControlMessageType, Type[ControlMessage]] = {  # type: ignore
    ControlMessageType.CONFIG: ConfigControlMessage,
    ControlMessageType.REPORT: ReportControlMessage,
    ControlMessageType.CLIENT_INFO: ClientInfoControlMessage,
}


def parse_control_message(message: dict) -> ControlMessage:  # type: ignore
    msg_type: ControlMessageType = ControlMessageType[message["message_type"]]

    try:
        message_class = control_types_dict[msg_type]
    except KeyError as e:
        logger.error("Invalid message type %s", msg_type)
        raise

    return message_class.model_validate(message)
