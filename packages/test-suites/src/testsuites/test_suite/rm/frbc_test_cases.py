import asyncio
from dataclasses import field
import logging
from typing import Dict, List
import uuid

from testsuites.certificate.certificate import (
    ComplianceReport,
)
from connectivity.config import FRBCRMTestConfig
from testsuites.controllers import FRBCRMController
from s2python.common import (
    ControlType as ProtocolControlType,
    Transition,
    InstructionStatus,
    ReceptionStatusValues,
    ReceptionStatus,
)
from testsuites.test_suite.test_suite import S2TestCase, TestLogger
from connectivity.s2_channel import S2Channel
from .base_test_case import NotControllableRMTestCase

from s2python.frbc import (
    FRBCActuatorStatus,
    FRBCStorageStatus,
    FRBCSystemDescription,
    FRBCUsageForecast,
    FRBCLeakageBehaviour,
    FRBCInstruction,
    FRBCOperationMode,
    FRBCActuatorDescription,
)
from testsuites.util import current_timezone_time

logger = logging.getLogger(__name__)


def dfs_traverse_transition_graph(
    current_op_mode: uuid.UUID,
    operation_modes: Dict[uuid.UUID, FRBCOperationMode],
    transitions: Dict[uuid.UUID, List[Transition]],
) -> List[Transition]:
    traversed = set()
    steps: List[Transition] = []

    stuck = False
    while not stuck:
        possible_transitions = transitions[current_op_mode]

        for transition in possible_transitions:
            if transition.id not in traversed:
                break
        if transition.id not in traversed:
            logger.info(
                "Transition from %s to %s",
                operation_modes[current_op_mode].diagnostic_label,
                operation_modes[transition.to].diagnostic_label,
            )
            current_op_mode = transition.to
            steps.append(transition)
            traversed.add(transition.id)
        else:
            stuck = True

    return steps


class FRBCTestCase(NotControllableRMTestCase):
    name = "FRBC Test Case"
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL

    controller: FRBCRMController
    config: FRBCRMTestConfig

    _system_description_received_event: asyncio.Event
    _initial_storage_status: asyncio.Event

    transitions_traversed: set

    def __init__(
        self,
        config: FRBCRMTestConfig,
        channel: S2Channel,
        controller: FRBCRMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

        self._system_description_received_event = asyncio.Event()
        self._initial_storage_status = asyncio.Event()

        self.message_handlers[FRBCSystemDescription] = (
            self.handle_frbc_system_description
        )
        self.message_handlers[FRBCUsageForecast] = self.handle_usage_forecast
        self.message_handlers[FRBCLeakageBehaviour] = self.handle_leakage_behaviour
        self.message_handlers[FRBCActuatorStatus] = self.handle_actuator_status
        self.message_handlers[FRBCStorageStatus] = self.handle_storage_status

        self.transitions_traversed = set()

    async def generate_tests(self):
        await super().generate_tests()

        # Wait until the system description received since this handler will add additional triggers based on actuators
        await self.add_trigger_method(
            None, wait_time=5, event=self._system_description_received_event
        )
        await self.add_trigger_method(
            None, wait_time=5, event=self._initial_storage_status
        )

    def update_system_description_precondition(
        self, precondition_id: str | None = None
    ):
        """Tests the system description precondition.

        Args:
            precondition_id (string): The ID from the S2 Specification
        """
        self.assertTrue(
            self.controller._system_description_received.is_set(),
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update System Description' not complete.",
        )
        self.test_logger.success(
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update System Description' is complete."
        )

    async def handle_frbc_system_description(
        self, message: FRBCSystemDescription, channel: "S2Channel", send_okay
    ):
        await self.handle_with_original_handler(message, channel, send_okay)

        await self.add_test_method(
            "Update FRBC System Description", self.validate_system_description, message
        )

        for actuator in self.controller.actuators.values():
            # Use a Graph Depth First Search to try traverse all of the operation modes.
            # This is a very simple DFS implementation so it can get stuck.
            # TODO: Use a more advanced traversal.
            steps = dfs_traverse_transition_graph(
                list(actuator.operation_modes.values())[0].id,
                actuator.operation_modes,
                actuator.from_transitions_map,
            )
            for transition in steps:
                await self.add_trigger_method(
                    self.send_operation_mode_transition_instruction,
                    actuator.id,
                    transition.to,
                    0,
                    wait_time=15,
                )

        logger.info("FRBC Test Received System Description.")
        self._system_description_received_event.set()

    async def send_operation_mode_transition_instruction(
        self,
        actuator_id: uuid.UUID,
        operation_mode_id: uuid.UUID,
        operation_mode_factor: int,
    ):
        instruction = FRBCInstruction(
            message_id=uuid.uuid4(),
            id=uuid.uuid4(),
            abnormal_condition=False,
            actuator_id=actuator_id,
            execution_time=current_timezone_time(),
            operation_mode=operation_mode_id,
            operation_mode_factor=operation_mode_factor,
        )

        reception_status = await self.controller.send_instruction_message(
            instruction, self.channel, raise_on_error=False
        )

        # Storage status is also passed here since this is added to a queue and by the time the validation is run the storage status might have changed.
        await self.add_test_method(
            "Test Correct Reception Status after sending Instruction.",
            self.validate_instruction_reception_status,
            instruction,
            reception_status,
            self.controller.storage_status,
        )

    async def validate_instruction_reception_status(
        self,
        instruction: FRBCInstruction,
        reception_status: ReceptionStatus,
        storage_status: FRBCStorageStatus,
    ):

        actuator = self.controller.actuators.get(instruction.actuator_id, None)
        if actuator is None:
            raise ValueError("Actuator not available.")

        operation_mode = actuator.operation_modes[instruction.operation_mode]

        within_operation_mode_range = False
        for element in operation_mode.elements:
            if (
                storage_status is not None
                and storage_status.present_fill_level
                > element.fill_level_range.start_of_range
                and storage_status.present_fill_level
                < element.fill_level_range.end_of_range
            ):
                within_operation_mode_range = True
                break

        # This check makes sure that if the reception status is OK then the storage level must be within the op mode's allowed range
        # and if the status is not OK then it should be outside of all of the allowed ranges.
        self.assertTrue(
            (
                reception_status.status == ReceptionStatusValues.OK
                and within_operation_mode_range
            )
            or (
                reception_status.status != ReceptionStatusValues.OK
                and not within_operation_mode_range
            )
        )

    async def setup(self):
        await self.controller._system_description_received.wait()

    async def handle_usage_forecast(
        self, message: FRBCUsageForecast, channel: "S2Channel", send_okay
    ):
        await self.handle_with_original_handler(message, channel, send_okay)
        await self.add_test_method(
            "9.6.5. Update Usage Forecast", self.validate_usage_forecast, message
        )
        await send_okay

    async def handle_leakage_behaviour(
        self, message: FRBCLeakageBehaviour, channel: "S2Channel", send_okay
    ):
        await self.handle_with_original_handler(message, channel, send_okay)
        await self.add_test_method(
            "9.6.3. Update Leakage Behaviour", self.validate_leakage_behaviour, message
        )
        await send_okay

    async def handle_actuator_status(
        self, message: FRBCLeakageBehaviour, channel: "S2Channel", send_okay
    ):
        await self.handle_with_original_handler(message, channel, send_okay)
        await self.add_test_method(
            "Update Actuator Status", self.validate_actuator_status, message
        )

    async def handle_storage_status(
        self, message: FRBCStorageStatus, channel: "S2Channel", send_okay
    ):
        # Get the old storage status before passing the new one to the handler
        await self.handle_with_original_handler(message, channel, send_okay)
        await self.add_test_method(
            "Update Storage Status",
            self.validate_storage_status,
            message,
        )

        # Just set it every time since we never reset it.
        self._initial_storage_status.set()

    async def validate_system_description(self, message: FRBCSystemDescription):
        # Sanity checks
        self.assertIsNotNone(message)  # Cannot be none.
        self.assertEqual(type(message), FRBCSystemDescription)

    async def validate_leakage_behaviour(self, message: FRBCLeakageBehaviour):
        self.update_system_description_precondition("9.6.3.2")

        # Sanity checks
        self.assertIsNotNone(message)
        self.assertEqual(type(message), FRBCLeakageBehaviour)

        if self.controller.system_description is None:
            raise AssertionError("System Description not set on controller.")

        self.assertTrue(
            self.controller.system_description.storage.provides_leakage_behaviour,
            "Received unexpected leakage behaviour.",
        )

    async def validate_actuator_status(self, message: FRBCActuatorStatus):
        self.update_system_description_precondition()

        # Sanity checks
        self.assertIsNotNone(message)
        self.assertEqual(type(message), FRBCActuatorStatus)

        instruction, instruction_status_update = (
            self.controller.get_latest_actuator_instruction(
                message.actuator_id, succeeded=True
            )
        )

        if instruction is None:
            return

        self.assertEqual(instruction.operation_mode, message.active_operation_mode_id)

    async def validate_storage_status(
        self,
        message: FRBCStorageStatus,
    ):
        self.update_system_description_precondition()

        # Sanity checks
        self.assertIsNotNone(message)
        self.assertEqual(type(message), FRBCStorageStatus)

        if self.controller.system_description is None:
            raise AssertionError("System Description not set on controller.")

        fill_range = self.controller.system_description.storage.fill_level_range

        self.assertTrue(
            message.present_fill_level < fill_range.end_of_range
            and message.present_fill_level > fill_range.start_of_range,
            "Storage fill level is outside of allowed range!",
        )

        # Could check the general trajectory for the storage status here based on the current operation modes
        # but this seems unnecessarily precise

    async def validate_usage_forecast(self, message: FRBCUsageForecast):
        self.update_system_description_precondition("9.6.5.2.")

        # Sanity checks
        self.assertIsNotNone(message)
        self.assertEqual(type(message), FRBCUsageForecast)

        if self.controller.system_description is None:
            raise AssertionError("System Description not set on controller.")

        self.assertTrue(
            self.controller.system_description.storage.provides_usage_forecast,
            "Received unexpected frbc usage forecast.",
        )
