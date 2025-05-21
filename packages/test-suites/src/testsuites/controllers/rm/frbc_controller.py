import asyncio
import logging
from typing import Optional
from s2python.common import ControlType as ProtocolControlType
from s2python.frbc import FRBCSystemDescription
from .base import BaseRMController


from connectivity.s2_channel import S2Channel

logger = logging.getLogger(__name__)


class FRBCRMController(BaseRMController):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL
    system_description: Optional[FRBCSystemDescription] = None

    _system_description_sent: asyncio.Event

    def __init__(self):
        super().__init__()
        self.system_description = None
        self._system_description_sent = asyncio.Event()

        self.add_handler(FRBCSystemDescription, self.handle_system_description_message)

    async def handle_system_description_message(
        self, message: FRBCSystemDescription, channel: "S2Channel", send_okay
    ):
        if not self.is_correct_message_type(message, FRBCSystemDescription):
            raise ValueError("Invalid Message Type.")

        logger.info("Received FRBC System Description.")
        self.system_description = message
        self._system_description_sent.set()

        await send_okay
