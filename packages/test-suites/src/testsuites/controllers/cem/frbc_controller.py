import asyncio
from bisect import bisect_right, insort
from dataclasses import dataclass, field
import datetime
import logging
from typing import Awaitable, Dict, List, Optional
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
    Timer,
    ReceptionStatus,
)
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class InstructionsStore:
    def __init__(self):
        self.instructions: Dict[uuid.UUID, List[FRBCInstruction]] = {}
        # self.instructions: List[FRBCInstruction] = []

    def add_instruction(self, obj: FRBCInstruction):
        # Keep instructions sorted
        if obj.actuator_id in self.instructions:
            insort(
                self.instructions[obj.actuator_id], obj, key=lambda i: i.execution_time
            )
        else:
            self.instructions[obj.actuator_id] = [obj]

    def get_active_instruction(
        self, actuator_id: uuid.UUID, timestamp: datetime
    ) -> Optional[FRBCInstruction]:
        if actuator_id not in self.instructions:
            return None

        timestamps = [
            instruction.execution_time for instruction in self.instructions[actuator_id]
        ]
        logger.info(
            "Getting instruction for timestamp %s. First in list = %s",
            timestamp,
            timestamps[0] if len(timestamps) > 0 else None,
        )
        idx = bisect_right(timestamps, timestamp) - 1
        if idx >= 0:
            return self.instructions[actuator_id][idx]
        return None


@dataclass
class ActuatorInformation:
    id = uuid.uuid4()
    diagnostic_label: str = ""
    supported_commodities: List[Commodity] = field(default_factory=list)

    # Map of the UUID to the operation mode
    operation_modes: Dict[uuid.UUID, FRBCOperationMode] = field(default_factory=dict)

    named_operation_modes: Dict[str, uuid.UUID] = field(default_factory=dict)

    # Map of the transition UUID to the transition
    transitions: Dict[uuid.UUID, Transition] = field(default_factory=dict)

    # Map from an operation mode to the transitions uuids which can be made
    transitions_from_to: Dict[uuid.UUID, List[uuid.UUID]] = field(default_factory=dict)

    # TODO: Not really sure what these are for
    timers: List[Timer] = field(default_factory=list)

    # actuator_status : FRBCActuatorStatus = None

    def add_operation_mode(
        self, mode: FRBCOperationMode, name: Optional[str] = None
    ) -> FRBCOperationMode:
        self.operation_modes[mode.id] = mode

        if name is not None:
            self.named_operation_modes[name] = mode.id

        return mode

    def get_operation_mode(self, id: uuid.UUID) -> FRBCOperationMode:
        return self.operation_modes[id]

    def get_named_operation_mode(self, name: str) -> FRBCOperationMode:
        id = self.named_operation_modes[name]
        return self.get_operation_mode(id)

    def add_transition(self, transition: Transition):
        self.transitions[transition.id] = transition

        if transition.from_ in self.transitions_from_to:
            self.transitions_from_to[transition.from_].append(transition.id)
        else:
            self.transitions_from_to[transition.from_] = [transition.id]

    def add_timer(self, timer):
        self.timers.append(timer)

    # def set_actuator_status(self, actuator_status : FRBCActuatorStatus):
    #     self.actuator_status = actuator_status

    def to_actuator_description(self):
        return FRBCActuatorDescription(
            id=self.id,
            diagnostic_label=self.diagnostic_label,
            timers=self.timers,
            operation_modes=[o for o in self.operation_modes.values()],
            supported_commodities=self.supported_commodities,
            transitions=[t for t in self.transitions.values()],
        )


class FRBCCEMController(NotControllableCEMController):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL

    leakage_behaviour: Optional[FRBCLeakageBehaviour] = None

    usage_forecast: Optional[FRBCUsageForecast] = None

    actuators: Dict[uuid.UUID, ActuatorInformation] = {}
    actuator_status: dict[uuid.UUID, FRBCActuatorStatus] = {}

    storage_status: Optional[FRBCStorageStatus] = None

    instructions: InstructionsStore

    def __init__(self, resource_manager_details: ResourceManagerDetails):
        super().__init__(resource_manager_details)

        self.instructions = InstructionsStore()

        self.add_handler(FRBCInstruction, self.handle_instruction)

    def add_actuator(self, actuator: ActuatorInformation):
        self.actuators[actuator.id] = actuator

    def set_storage_description(self, storage_description: FRBCStorageDescription):
        self.storage_description = storage_description

    def set_leakage_behaviour(self, leakage_behaviour: FRBCLeakageBehaviour):
        self.leakage_behaviour = leakage_behaviour

    def generate_system_description(self):
        if self.storage_description is None:
            raise ValueError("Storage description must be set.")

        self.system_description = FRBCSystemDescription(
            message_id=uuid.uuid4(),
            valid_from=current_timezone_time(),
            actuators=[a.to_actuator_description() for a in self.actuators.values()],
            storage=self.storage_description,
        )
        return self.system_description

    def get_active_operation_mode(self, actuator_id: uuid.UUID):
        actuator_status = self.actuator_status[actuator_id]

        operation_mode = self.actuators[actuator_id].operation_modes[
            actuator_status.active_operation_mode_id
        ]

        return operation_mode

    async def send_frbc_system_description(
        self, channel: Optional[S2Channel]
    ) -> tuple[FRBCSystemDescription, ReceptionStatus]:
        if channel is None:
            raise ValueError("Channel not set.")

        logger.info("Sending FRBC system description")
        system_description = self.generate_system_description()
        reception_status = await channel.send_msg_and_await_reception_status(
            system_description, raise_on_error=False
        )
        return system_description, reception_status

    async def revoke_frbc_system_description(self, channel: Optional[S2Channel]):
        if channel is None:
            raise ValueError("Channel not set.")

        if self.system_description_id is None:
            raise ValueError("No System Description is set.")

        reception_status = await channel.send_msg_and_await_reception_status(
            RevokeObject(
                message_id=uuid.uuid4(),
                object_id=self.system_description_id,
                object_type=RevokableObjects.FRBC_SystemDescription,
            ),
            raise_on_error=False,
        )

        self.system_description_id = None
        return reception_status

    async def update_frbc_leakage_behavior(
        self, channel: Optional[S2Channel]
    ) -> ReceptionStatus:
        if channel is None:
            raise ValueError("Channel not set.")

        if self.leakage_behaviour is None:
            raise ValueError("Leakage behavior not set.")

        reception_status = await channel.send_msg_and_await_reception_status(
            self.leakage_behaviour, raise_on_error=False
        )

        return reception_status

    async def revoke_leakage_behaviour(self, channel: Optional[S2Channel]):
        if channel is None:
            raise ValueError("Channel not set.")

        raise NotImplementedError(
            "Revoke FRBC Leakage Behaviour Message not implemented in S2 Python."
        )

        # self.leakage_behaviour = None
        # return reception_status

    async def update_frbc_usage_forecast(
        self, channel: Optional[S2Channel], forecast: FRBCUsageForecast
    ) -> ReceptionStatus:
        if channel is None:
            raise ValueError("Channel not set.")

        reception_status = await channel.send_msg_and_await_reception_status(
            forecast, raise_on_error=False
        )

        return reception_status

    async def update_actuator_status(
        self, channel: Optional[S2Channel], actuator_status: FRBCActuatorStatus
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        reception_status = await channel.send_msg_and_await_reception_status(
            actuator_status, raise_on_error=False
        )

        self.actuator_status[actuator_status.actuator_id] = actuator_status

        return reception_status

    async def update_storage_status(
        self, channel: Optional[S2Channel], storage_status: FRBCStorageStatus
    ):
        if channel is None:
            raise ValueError("Channel not set.")

        reception_status = await channel.send_msg_and_await_reception_status(
            storage_status, raise_on_error=False
        )

        self.storage_status = storage_status

        return reception_status

    async def send_instruction_status_update(
        self, channel: "S2Channel", instruction_status_update: InstructionStatusUpdate
    ):
        reception_status = await channel.send_msg_and_await_reception_status(
            instruction_status_update, raise_on_error=False
        )
        return reception_status

    async def handle_instruction(
        self, instruction: FRBCInstruction, channel: S2Channel, send_okay: Awaitable
    ):
        logger.info("Instruction: %s", instruction)

        self.instructions.add_instruction(instruction)

        await send_okay
        update = InstructionStatusUpdate(
            message_id=uuid.uuid4(),
            instruction_id=instruction.id,
            status_type=InstructionStatus.SUCCEEDED,
            timestamp=current_timezone_time(),
        )

        reception_status = await channel.send_msg_and_await_reception_status(
            update, raise_on_error=False
        )

        # return update, reception_status
