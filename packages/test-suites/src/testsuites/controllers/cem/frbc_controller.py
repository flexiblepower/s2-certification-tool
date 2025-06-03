import asyncio
import datetime
import logging
from typing import Awaitable, Optional
import uuid
from s2python.common import ControlType as ProtocolControlType
from s2python.frbc import (
    FRBCSystemDescription,
    FRBCLeakageBehaviour,
    FRBCStorageDescription,
    FRBCActuatorDescription,
    FRBCOperationMode,
    FRBCOperationModeElement,
    FRBCInstruction,
    FRBCActuatorStatus,
    FRBCUsageForecast,
    FRBCStorageStatus,
)

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


class FRBCCEMController(NotControllableCEMController):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL
    system_description: Optional[FRBCSystemDescription] = None

    leakage_behaviour: Optional[FRBCLeakageBehaviour] = None

    usage_forecast: Optional[FRBCUsageForecast] = None

    actuator_status: dict[uuid.UUID, FRBCActuatorStatus] = {}

    def __init__(self, resource_manager_details: ResourceManagerDetails):
        super().__init__(resource_manager_details)

        self.add_handler(FRBCInstruction, self.handle_instruction)

    async def handle_instruction(
        self, message: FRBCInstruction, channel: S2Channel, send_okay: Awaitable
    ):

        logger.info(message)

        await send_okay

    async def send_frbc_system_description(
        self, channel: Optional[S2Channel], system_description: FRBCSystemDescription
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        logger.info("Sending FRBC system description")
        await channel.send_msg_and_await_reception_status(system_description)
        self.system_description = system_description

    async def revoke_frbc_system_description(self, channel: Optional[S2Channel]):
        if channel is None:
            raise ValueError("Channel not set.")

        if self.system_description is None:
            raise ValueError("No System Description is set.")

        await channel.send_msg_and_await_reception_status(
            RevokeObject(
                message_id=uuid.uuid4(),
                object_id=self.system_description.message_id,
                object_type=RevokableObjects.FRBC_SystemDescription,
            )
        )

        self.system_description = None

    async def send_frbc_leakage_behavior(
        self, channel: Optional[S2Channel], leakage_behaviour: FRBCLeakageBehaviour
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        await channel.send_msg_and_await_reception_status(leakage_behaviour)

        self.leakage_behaviour = leakage_behaviour

    async def revoke_leakage_behaviour(self, channel: Optional[S2Channel]):
        if channel is None:
            raise ValueError("Channel not set.")

        raise NotImplementedError(
            "Revoke FRBC Leakage Behaviour Message not implemented in S2 Python."
        )

        self.leakage_behaviour = None

    async def send_frbc_usage_forecast(
        self, channel: Optional[S2Channel], forecast: FRBCUsageForecast
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        await channel.send_msg_and_await_reception_status(forecast)

        self.usage_forecast

    async def send_actuator_status(
        self, channel: Optional[S2Channel], actuator_status: FRBCActuatorStatus
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        await channel.send_msg_and_await_reception_status(actuator_status)

        self.actuator_status[actuator_status.actuator_id] = actuator_status

    async def send_storage_status(
        self, channel: Optional[S2Channel], storage_status: FRBCStorageStatus
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        await channel.send_msg_and_await_reception_status(storage_status)

        self.storage_status = storage_status

    async def send_instruction_status_update(
        self, channel: "S2Channel", instruction_status_update: InstructionStatusUpdate
    ):
        await channel.send_msg_and_await_reception_status(instruction_status_update)
