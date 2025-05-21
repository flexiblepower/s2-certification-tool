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
)
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
)
import logging

logger = logging.getLogger(__name__)


class FRBCCEMController(BaseCEMController):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL
    system_description: Optional[FRBCSystemDescription] = None

    actuator_status: Optional[FRBCActuatorStatus]

    def __init__(self, resource_manager_details: ResourceManagerDetails):
        super().__init__(resource_manager_details)

    async def send_frbc_system_description(
        self, channel: Optional[S2Channel], system_description: FRBCSystemDescription
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        logger.info("Sending FRBC system description")
        await channel.send_msg_and_await_reception_status(system_description)
        self.system_description = system_description

    async def send_frbc_leakage_behavior(
        self, channel: Optional[S2Channel], leakage_behaviour: FRBCLeakageBehaviour
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        await channel.send_msg_and_await_reception_status(leakage_behaviour)

    async def handle_instruction(
        self,
        message: FRBCInstruction,
        channel: "S2Channel",
        send_okay: Awaitable,
    ):
        logger.info(message)

        await channel.send_msg_and_await_reception_status(
            InstructionStatusUpdate(
                instruction_id=message.id,
                message_id=uuid.uuid4(),
                status_type=InstructionStatus.SUCCEEDED,
                timestamp=datetime.datetime.now(tz=datetime.timezone.utc),
            )
        )
