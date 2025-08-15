import asyncio
import datetime
from typing import Awaitable, List, Optional
import uuid

from s2python.common import (
    ControlType as ProtocolControlType,
    InstructionStatusUpdate,
    ReceptionStatus,
)
from s2python.pebc import (
    PEBCEnergyConstraint,
    PEBCPowerConstraints,
    PEBCInstruction,
    PEBCPowerEnvelope,
)

from testsuites.util import current_timezone_time
from .base import BaseRMController
from connectivity.s2_channel import S2Channel

import logging

logger = logging.getLogger(__name__)


class PEBCRMController(BaseRMController):
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL
    power_constraints: List[PEBCPowerConstraints] = []
    energy_constraints: List[PEBCEnergyConstraint] = []

    def __init__(self):
        super().__init__()

        self.add_handler(PEBCPowerConstraints, self.handle_power_constraints_message)
        self.add_handler(PEBCEnergyConstraint, self.handle_energy_constraints_message)
        self.add_handler(InstructionStatusUpdate, self.handle_instruction_status_update)

    async def handle_power_constraints_message(
        self,
        message: PEBCPowerConstraints,
        channel: "S2Channel",
        send_okay: Awaitable,
    ):
        self.power_constraints.append(message)

        await send_okay

    async def handle_energy_constraints_message(
        self,
        message: PEBCEnergyConstraint,
        connection: "S2Channel",
        send_okay: Awaitable,
    ):
        self.energy_constraints.append(message)
        await send_okay

    async def handle_instruction_status_update(
        self,
        message: InstructionStatusUpdate,
        connection: "S2Channel",
        send_okay: Awaitable,
    ):
        await send_okay

    def get_power_constraint(
        self,
        valid_from: datetime.datetime,
        valid_until: datetime.datetime | None = None,
    ) -> PEBCPowerConstraints | None:
        """Gets power constraint which the provided range fits into."""

        # current_time = current_timezone_time()
        for power_constraint in reversed(self.power_constraints):

            if power_constraint.valid_from < valid_from:
                if valid_until is None or power_constraint.valid_until is None:
                    return power_constraint
                elif power_constraint.valid_until > valid_until:
                    return power_constraint
        return None

    async def send_power_envelope_instruction(
        self,
        channel: "S2Channel",
        power_envelopes: List[PEBCPowerEnvelope],
        execution_time: datetime.datetime = datetime.datetime.now(
            datetime.timezone.utc
        ),
    ) -> tuple[PEBCInstruction, ReceptionStatus]:

        power_constraint = self.get_power_constraint(current_timezone_time())

        if power_constraint is None:
            raise ValueError("Power Constraints not set.")

        instruction = PEBCInstruction(
            message_id=uuid.uuid4(),
            id=uuid.uuid4(),  # ? TODO: Should this be a new UUID?
            power_constraints_id=power_constraint.id,
            power_envelopes=power_envelopes,
            # Make it timezone-aware (UTC)
            execution_time=execution_time,
            abnormal_condition=False,
        )

        reception_status = await channel.send_msg_and_await_reception_status(
            instruction, 5, raise_on_error=False
        )

        return instruction, reception_status
