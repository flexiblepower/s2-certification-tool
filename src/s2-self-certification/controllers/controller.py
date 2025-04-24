from typing import Callable, Type
from message_handlers import MessageHandler
from s2python.common import ControlType as ProtocolControlType
from s2python.message import S2Message
from s2python.s2_validation_error import S2ValidationError

import logging

logger = logging.getLogger(__name__)


class Controller(MessageHandler):
    control_type: ProtocolControlType

    def __init__(self):
        super().__init__()

    def handle_s2_validation_exception(self, e: S2ValidationError):
        logger.error("Failed to validate S2 Message.")
        logger.error(e.pydantic_validation_error)


class BaseController(Controller):
    control_type = ProtocolControlType.NOT_CONTROLABLE

    def __init__(self):
        super().__init__()
