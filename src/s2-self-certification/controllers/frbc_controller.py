from s2python.common import ControlType as ProtocolControlType
from .controller import Controller


class FRBCController(Controller):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL

    def __init__(self):
        super().__init__()
