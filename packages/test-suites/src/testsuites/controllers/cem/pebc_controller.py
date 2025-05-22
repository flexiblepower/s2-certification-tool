import asyncio
import datetime
import logging
from typing import Awaitable, Optional
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
)
import logging

logger = logging.getLogger(__name__)


class PEBCCEMController(NotControllableCEMController):
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL

    energy_constraint: Optional[PEBCEnergyConstraint] = None
    power_constraint: Optional[PEBCPowerConstraints] = None

    def __init__(self, resource_manager_details: ResourceManagerDetails):
        super().__init__(resource_manager_details)

    async def send_pebc_energy_constraint(
        self, channel: Optional[S2Channel], energy_constraints: PEBCEnergyConstraint
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        await channel.send_msg_and_await_reception_status(energy_constraints)

        self.energy_constraint = energy_constraints

    async def send_pebc_power_constraint(
        self, channel: Optional[S2Channel], power_constraints: PEBCPowerConstraints
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        await channel.send_msg_and_await_reception_status(power_constraints)

        self.power_constraint = power_constraints
