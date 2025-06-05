import asyncio
import datetime
import logging
from typing import Awaitable, List, Optional
import uuid
from s2python.common import ControlType as ProtocolControlType
from s2python.pebc import PEBCEnergyConstraint, PEBCPowerConstraints, PEBCInstruction

from testsuites.controllers.cem.not_controllable_controller import (
    NotControllableCEMController,
)
from testsuites.util import current_timezone_time
from .base import BaseCEMController
from connectivity.s2_channel import S2Channel

from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    PowerForecast,
    PowerMeasurement,
    ResourceManagerDetails,
    Handshake,
    NumberRange,
    Commodity,
    PowerRange,
    CommodityQuantity,
    Transition,
    Duration,
    InstructionStatusUpdate,
    InstructionStatus,
    RevokeObject,
    RevokableObjects,
    ReceptionStatus,
)
import logging

logger = logging.getLogger(__name__)


class PEBCCEMController(NotControllableCEMController):
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL

    energy_constraint: Optional[PEBCEnergyConstraint] = None
    power_constraint: Optional[PEBCPowerConstraints] = None

    instructions: List[PEBCInstruction] = []

    def __init__(self, resource_manager_details: ResourceManagerDetails):
        super().__init__(resource_manager_details)

    async def send_pebc_power_constraint(
        self, channel: Optional[S2Channel], power_constraints: PEBCPowerConstraints
    ) -> ReceptionStatus:
        if channel is None:
            raise ValueError("Channel not set.")

        reception_status = await channel.send_msg_and_await_reception_status(
            power_constraints, raise_on_error=False
        )

        self.power_constraint = power_constraints

        return reception_status

    async def revoke_pebc_power_constraint(
        self, channel: Optional[S2Channel]
    ) -> ReceptionStatus:
        if channel is None:
            raise ValueError("Channel not set.")

        if self.power_constraint is None:
            raise ValueError("No Power Constraint to Revoke.")

        reception_status = await channel.send_msg_and_await_reception_status(
            RevokeObject(
                message_id=uuid.uuid4(),
                object_id=self.power_constraint.message_id,
                object_type=RevokableObjects.PEBC_PowerConstraints,
            ),
            raise_on_error=False,
        )
        self.power_constraint = None
        return reception_status

    async def send_pebc_energy_constraint(
        self, channel: Optional[S2Channel], energy_constraints: PEBCEnergyConstraint
    ) -> ReceptionStatus:
        if channel is None:
            raise ValueError("Channel not set.")

        reception_status = await channel.send_msg_and_await_reception_status(
            energy_constraints, raise_on_error=False
        )

        self.energy_constraint = energy_constraints
        return reception_status

    async def revoke_pebc_energy_constraint(
        self, channel: Optional[S2Channel]
    ) -> ReceptionStatus:
        if channel is None:
            raise ValueError("Channel not set.")

        if self.energy_constraint is None:
            raise ValueError("No Energy Constraint to Revoke.")

        reception_status = await channel.send_msg_and_await_reception_status(
            RevokeObject(
                message_id=uuid.uuid4(),
                object_id=self.energy_constraint.message_id,
                object_type=RevokableObjects.PEBC_EnergyConstraint,
            ),
            raise_on_error=False,
        )
        self.energy_constraint = None
        return reception_status

    async def handle_revoke(
        self, revoke_message: RevokeObject, channel: S2Channel, send_okay: Awaitable
    ):
        if revoke_message.object_type == RevokableObjects.PEBC_Instruction:
            for i, instruction in enumerate(self.instructions):
                if instruction.id == revoke_message.object_id:
                    self.instructions.pop(i)
                    break
        await send_okay
