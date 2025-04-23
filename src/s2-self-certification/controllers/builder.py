from typing import Callable, Type
from controllers.controller import Controller
from s2python.message import S2Message


class ControlTypeBuilder:
    def __init__(self):
        self.control_type = Controller()

    def with_handler(self, msg_type: Type[S2Message], handler: Callable):
        self.control_type.add_handler(msg_type, handler)
        return self

    def build(self):
        return self.control_type
