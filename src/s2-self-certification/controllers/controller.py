from typing import Callable, Type
from message_handlers import MessageHandler
from s2python.common import ControlType as ProtocolControlType
from s2python.message import S2Message


class Controller(MessageHandler):
    control_type: ProtocolControlType

    def __init__(self):
        super().__init__()

