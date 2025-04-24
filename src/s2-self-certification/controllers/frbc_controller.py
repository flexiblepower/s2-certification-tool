import asyncio
import logging
from typing import Optional
from connection import Connection
from s2python.common import ControlType as ProtocolControlType
from s2python.frbc import FRBCSystemDescription
from .controller import Controller

logger = logging.getLogger(__name__)


class FRBCController(Controller):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL
    system_description: FRBCSystemDescription

    _system_description_received: asyncio.Event

    def __init__(self):
        super().__init__()
        self._system_description_received = asyncio.Event()

    async def handle_power_constraints_message(
        self, message: FRBCSystemDescription, connection: "Connection", send_okay
    ):
        if not self.is_correct_message_type(message, FRBCSystemDescription):
            raise ValueError("Invalid Message Type.")

        logger.info("Received FRBC System Description.")
        self.system_description = message
        self._system_description_received.set()

        await send_okay
