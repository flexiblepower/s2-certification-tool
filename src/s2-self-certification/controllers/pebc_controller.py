import asyncio
from typing import TYPE_CHECKING, Optional

from s2python.common import ControlType as ProtocolControlType
from s2python.pebc import (
    PEBCPowerConstraints,
)
from .controller import Controller

if TYPE_CHECKING:
    from connection import Connection

import logging

logger = logging.getLogger(__name__)


class PEBCController(Controller):
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL
    power_constraints: Optional[PEBCPowerConstraints]

    _power_constraints_received = asyncio.Event()

    def __init__(self):
        super().__init__()

        self.power_constraints = None
        self._power_constraints_received = asyncio.Event()

        self.add_handler(PEBCPowerConstraints, self.handle_power_constraints_message)
        # self.add_handler(PEBCEnergyConstraint, self.handle_energy_constraints_message)
        # self.add_handler(PowerMeasurement, self.handle_power_measurement_message)
        # self.add_handler(PowerForecast, self.handle_power_forecast_message)
        # self.add_handler(InstructionStatusUpdate, self.handle_instruction_status_update)

    async def handle_power_constraints_message(
        self, message: PEBCPowerConstraints, connection: "Connection", send_okay
    ):
        if not self.is_correct_message_type(message, PEBCPowerConstraints):
            raise ValueError("Invalid Message Type.")

        logger.info("Received power constraints.")
        self.power_constraints = message
        self._power_constraints_received.set()

        await send_okay

    # async def handle_energy_constraints_message(
    #     self, message: S2Message, connection, send_okay
    # ):
    #     if not self.is_correct_message_type(message, PEBCEnergyConstraint):
    #         logger.error(
    #             "Invalid Message Type. Expected %s but received %s",
    #             PEBCEnergyConstraint.message_type,
    #             message.message_type,
    #         )
    #         raise ValueError("Invalid Message Type.")

    #     await send_okay

    # async def handle_power_measurement_message(self, message, connection, send_okay):
    #     self.is_correct_message_type(message, PowerMeasurement)
    #     await send_okay

    # async def handle_power_forecast_message(self, message, connection, send_okay):
    #     self.is_correct_message_type(message, PowerForecast)
    #     await send_okay

    # async def handle_instruction_status_update(
    #     self, message: InstructionStatusUpdate, connection, send_okay
    # ):
    #     await send_okay
