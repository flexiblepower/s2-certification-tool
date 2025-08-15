import asyncio
from dataclasses import dataclass
import logging
from typing import Dict, List, Optional, Tuple
import uuid
from s2python.common import (
    ControlType as ProtocolControlType,
    Transition,
    InstructionStatusUpdate,
    InstructionStatus,
)
from s2python.frbc import (
    FRBCSystemDescription,
    FRBCInstruction,
    FRBCOperationMode,
    FRBCStorageStatus,
    FRBCActuatorDescription,
    FRBCActuatorStatus,
)
from .base import BaseRMController


from connectivity.s2_channel import S2Channel

logger = logging.getLogger(__name__)


@dataclass
class ActuatorInfo:
    id: uuid.UUID
    actuator: FRBCActuatorDescription
    operation_modes: Dict[uuid.UUID, FRBCOperationMode]
    from_transitions_map: Dict[uuid.UUID, List[Transition]]


class FRBCRMController(BaseRMController):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL

    system_description: Optional[FRBCSystemDescription] = None

    # operation_mode: Optional[FRBCOperationMode] = None
    # # operation_modes : Dict[uuid.UUID, FRBCOperationMode]= {}
    actuators: Dict[uuid.UUID, ActuatorInfo] = {}
    actuator_status: Dict[uuid.UUID, FRBCActuatorStatus] = {}
    storage_status: Optional[FRBCStorageStatus] = None

    # Map of instruction ID to a tuple containing the instruction and the status update
    instructions: Dict[
        uuid.UUID, Tuple[FRBCInstruction, InstructionStatusUpdate | None]
    ] = {}
    # A list of instructions to know the order in which the instructions were executed.
    instruction_ordering: List[FRBCInstruction] = []

    _system_description_received: asyncio.Event

    def __init__(self):
        super().__init__()
        self.system_description = None
        self._system_description_received = asyncio.Event()

        self.add_handler(FRBCSystemDescription, self.handle_system_description_message)
        self.add_handler(FRBCStorageStatus, self.handle_storage_status)
        self.add_handler(FRBCActuatorStatus, self.handle_actuator_status)

    async def handle_system_description_message(
        self, message: FRBCSystemDescription, channel: "S2Channel", send_okay
    ):
        logger.info("Received FRBC System Description.")
        self.system_description = message
        self._system_description_received.set()

        for actuator in message.actuators:
            op_modes = {}
            transitions: Dict[uuid.UUID, List[Transition]] = {}

            for operation_mode in actuator.operation_modes:
                op_modes[operation_mode.id] = operation_mode

            for transition in actuator.transitions:
                if transition.from_ in transitions:
                    transitions[transition.from_].append(transition)
                else:
                    transitions[transition.from_] = [transition]

            self.actuators[actuator.id] = ActuatorInfo(
                id=actuator.id,
                actuator=actuator,
                operation_modes=op_modes,
                from_transitions_map=transitions,
            )

        await send_okay

    async def handle_storage_status(
        self, message: FRBCStorageStatus, channel: "S2Channel", send_okay
    ):
        self.storage_status = message
        await send_okay

    async def handle_actuator_status(
        self, message: FRBCActuatorStatus, channel: "S2Channel", send_okay
    ):
        self.actuator_status[message.actuator_id] = message
        await send_okay

    async def send_instruction_message(
        self, message: FRBCInstruction, channel: "S2Channel", raise_on_error=True
    ):

        actuator_info = self.actuators[message.actuator_id]
        from_op_mode = None
        if self.actuator_status.get(actuator_info.id, None) is not None:
            from_op_mode = actuator_info.operation_modes[
                self.actuator_status[actuator_info.id].active_operation_mode_id
            ].diagnostic_label
        to_op_mode = actuator_info.operation_modes[
            message.operation_mode
        ].diagnostic_label

        logger.info(
            "Sending Transition Instruction for actuator %s. From %s to %s",
            actuator_info.actuator.diagnostic_label,
            from_op_mode,
            to_op_mode,
        )

        self.instructions[message.id] = (message, None)
        self.instruction_ordering.append(message)

        return await channel.send_msg_and_await_reception_status(
            message, 5, raise_on_error=raise_on_error
        )

    async def handle_instruction_status_update(
        self, message: InstructionStatusUpdate, channel: "S2Channel", send_okay
    ):

        self.instructions[message.instruction_id] = (
            self.instructions[message.instruction_id][0],
            message,
        )

        await send_okay

    def get_latest_actuator_instruction(
        self, actuator_id: uuid.UUID, succeeded=False
    ) -> tuple[FRBCInstruction | None, InstructionStatusUpdate | None]:
        """Retrieves the most recent instruction for a given actuator
        If succeeded param is True then it will skip rejected instructions.
        """

        for instruction in reversed(self.instruction_ordering):
            if instruction.actuator_id == actuator_id:
                _, status = self.instructions[instruction.id]
                if (
                    succeeded and status == InstructionStatus.SUCCEEDED
                ) or not succeeded:
                    return instruction, status

        return (None, None)
