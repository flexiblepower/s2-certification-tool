import asyncio
from dataclasses import dataclass
import logging
from typing import Dict, List, Optional, Tuple
import uuid

from testsuites.certificate.certificate import (
    ComplianceReport,
)
from connectivity.config import PEBCRMTestConfig
from connectivity.s2_channel import S2Channel
from testsuites.controllers import PEBCRMController

from testsuites.test_suite.rm.base_test_case import NotControllableRMTestCase
from testsuites.test_suite.test_suite import (
    NotApplicableTestException,
    S2TestCase,
    TestLogger,
)
from testsuites.certificate.certificate import (
    TestResultStatus,
)
from s2python.common import (
    ControlType as ProtocolControlType,
    InstructionStatusUpdate,
    CommodityQuantity,
    NumberRange,
    InstructionStatus,
    ReceptionStatus,
    Duration,
)
from s2python.pebc import (
    PEBCAllowedLimitRange,
    PEBCPowerConstraints,
    PEBCPowerEnvelope,
    PEBCPowerEnvelopeElement,
    PEBCPowerEnvelopeLimitType,
    PEBCEnergyConstraint,
    PEBCInstruction,
)

from itertools import product

from testsuites.util import current_timezone_time

logger = logging.getLogger(__name__)


@dataclass
class InstructionTestState:
    instruction: PEBCInstruction
    reception_status: ReceptionStatus
    expected_status: InstructionStatus
    status_update: Optional[InstructionStatusUpdate] = None


class PEBCTestCase(NotControllableRMTestCase):
    name = "9.3. Power Envelope Based Control Tasks"
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL
    controller: PEBCRMController
    config: PEBCRMTestConfig

    _power_constraints_received_event: asyncio.Event
    _energy_constraints_received_event: asyncio.Event

    instruction_test_states: Dict[uuid.UUID, InstructionTestState] = {}

    def __init__(
        self,
        config: PEBCRMTestConfig,
        channel: S2Channel,
        controller: PEBCRMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

        self._power_constraints_received_event = asyncio.Event()
        self._energy_constraints_received_event = asyncio.Event()

        self.message_handlers[PEBCEnergyConstraint] = self.handle_energy_constraints
        self.message_handlers[PEBCPowerConstraints] = self.handle_power_constraints
        self.message_handlers[InstructionStatusUpdate] = (
            self.handle_instruction_status_update
        )

    async def generate_tests(self):
        await super().generate_tests()

        await self.add_trigger_method(
            None, wait_time=None, event=self._power_constraints_received_event
        )

        if self.config.sends_energy_constraints:
            await self.add_trigger_method(
                None,
                wait_time=self.config.energy_constraints_wait_timeout,
                event=self._power_constraints_received_event,
            )

    async def control_type_set_pebc_precondition(
        self, precondition_id: str | None = None
    ):
        """Tests the system description precondition.

        Args:
            precondition_id (string): The ID from the S2 Specification
        """
        # try:
        self.assertEqual(
            self.controller.control_type,
            ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL,
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Activate Control Type' where ControlType is PEBC not complete.",
        )
        self.test_logger.success(
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Activate Control Type' where ControlType is PEBC is complete.",
        )

    async def handle_power_constraints(
        self, message: PEBCPowerConstraints, channel: "S2Channel", send_okay
    ):
        await self.handle_with_original_handler(message, channel, send_okay)

        await self.add_test_method(
            "Update PEBC Power Constraint", self.validate_power_constraints, message
        )

        # First phase of testing is just letting the RM send readings. Energy constraints will be waited for first.
        await self.add_trigger_method(
            None, wait_time=self.config.instruction_trigger_wait_time, event=None
        )

        # Generate curtailment instruction triggers.
        await self.generate_set_limit_range_instruction_triggers()

        self._power_constraints_received_event.set()

    async def handle_energy_constraints(
        self, message: PEBCEnergyConstraint, channel: "S2Channel", send_okay
    ):
        await self.handle_with_original_handler(message, channel, send_okay)

        await self.add_test_method(
            "Update PEBC Energy Constraint", self.validate_energy_constraints, message
        )
        self._energy_constraints_received_event.set()

    async def handle_instruction_status_update(
        self, message: InstructionStatusUpdate, channel: "S2Channel", send_okay
    ):
        await send_okay

        await self.add_test_method(
            "Validate Instruction Status Update",
            self.validate_instruction_status_update,
            message,
        )

    async def validate_instruction_status_update(
        self, instruction_status_update: InstructionStatusUpdate
    ):

        self.assertIsNotNone(instruction_status_update)
        self.assertEqual(type(instruction_status_update), InstructionStatusUpdate)

        state = self.instruction_test_states.get(
            instruction_status_update.instruction_id, None
        )

        if state is None:
            raise AssertionError("Instruction not recognised. State doesn't exist.")

        instruction = state.instruction

        # Sanity Checks
        self.assertIsNotNone(instruction)
        self.assertEqual(type(instruction), PEBCInstruction)
        self.assertEqual(instruction_status_update.instruction_id, instruction.id)

        # Check that the status matches what we expect given the range we provided.
        self.assertEqual(
            instruction_status_update.status_type,
            state.expected_status,
            f"Instruction status {instruction_status_update.status_type} does not match expected {state.expected_status}",
        )

    async def validate_power_constraints(self, power_constraint: PEBCPowerConstraints):
        await self.control_type_set_pebc_precondition("9.3.1.2.")

        self.assertIsNotNone(power_constraint)
        self.assertEqual(type(power_constraint), PEBCPowerConstraints)

    async def validate_energy_constraints(
        self,
        energy_constraint: PEBCEnergyConstraint,
    ):
        await self.control_type_set_pebc_precondition("9.3.1.2.")
        self.assertIsNotNone(energy_constraint)
        self.assertEqual(type(energy_constraint), PEBCEnergyConstraint)

        power_constraint = self.controller.get_power_constraint(
            energy_constraint.valid_from, energy_constraint.valid_until
        )

        self.assertIsNotNone(
            power_constraint,
            f"Provided energy constraint does not fit withing the valid_from/to range of the power constraints.",
        )

    def create_power_envelope(
        self, commodity_quantity, lower_limit, upper_limit, duration=3600
    ) -> PEBCPowerEnvelope:
        return PEBCPowerEnvelope(
            id=str(uuid.uuid4()),  # type: ignore
            commodity_quantity=commodity_quantity,
            power_envelope_elements=[
                PEBCPowerEnvelopeElement(
                    lower_limit=lower_limit,
                    upper_limit=upper_limit,
                    duration=Duration(duration),
                )
            ],
        )

    async def send_power_envelope(
        self,
        commodity_quantity: CommodityQuantity,
        lower_limit: NumberRange,
        upper_limit: NumberRange,
        duration: int,
        expected_instruction_status: InstructionStatus,
    ):
        self.test_logger.info(
            f"Sending instruction with expected instruction status {expected_instruction_status}"
        )

        power_envelope = self.create_power_envelope(
            commodity_quantity=commodity_quantity,
            lower_limit=lower_limit,
            upper_limit=upper_limit,
            duration=duration,
        )

        instruction, reception_status = (
            await self.controller.send_power_envelope_instruction(
                self.channel, [power_envelope]
            )
        )

        self.instruction_test_states[instruction.id] = InstructionTestState(
            instruction=instruction,
            reception_status=reception_status,
            expected_status=expected_instruction_status,
        )

        # Wait the specified instruction processing time before proceeding.
        if (
            self.controller.resource_manager_details
            and self.config.wait_instruction_processing_time
        ):
            wait_time = (
                self.controller.resource_manager_details.instruction_processing_delay.to_timedelta().seconds
            )
            await asyncio.sleep(wait_time)

    async def generate_curtail_commodity_quantity_instruction_triggers(
        self,
        commodity_quantity: CommodityQuantity,
        limit_ranges: List[PEBCAllowedLimitRange],
        duration=3600,
    ):
        """This function generates a curtailment instruction trigger for each combination of upper and lower limits."""

        logger.info("Curtailing %s", commodity_quantity)

        lower_limits: List[NumberRange] = []
        upper_limits: List[NumberRange] = []

        for limit in limit_ranges:
            if limit.limit_type == PEBCPowerEnvelopeLimitType.LOWER_LIMIT:
                lower_limits.append(limit.range_boundary)
            else:
                upper_limits.append(limit.range_boundary)

        limit_range_pairs: List[Tuple[NumberRange, NumberRange]] = list(
            product(lower_limits, upper_limits)
        )

        limits = []
        for lower_limit, upper_limit in limit_range_pairs:
            limits += [
                (lower_limit.start_of_range, upper_limit.start_of_range),
                (lower_limit.start_of_range, upper_limit.end_of_range),
                (lower_limit.end_of_range, upper_limit.start_of_range),
                (lower_limit.end_of_range, upper_limit.end_of_range),
            ]

        # Remove duplicates
        limits = list(set(limits))

        for lower, upper in limits:
            await self.add_trigger_method(
                self.send_power_envelope,
                commodity_quantity=commodity_quantity,
                lower_limit=lower,
                upper_limit=upper,
                duration=duration,
                expected_instruction_status=InstructionStatus.SUCCEEDED,
                wait_time=self.config.instruction_trigger_wait_time,
            )

            await self.add_trigger_method(
                self.send_power_envelope,
                commodity_quantity=commodity_quantity,
                lower_limit=lower_limit.end_of_range - 1,
                upper_limit=upper_limit.start_of_range + 1,
                duration=duration,
                expected_instruction_status=InstructionStatus.REJECTED,
                wait_time=self.config.instruction_trigger_wait_time,
            )

    async def generate_set_limit_range_instruction_triggers(self):
        # TODO: During the time waiting for all of the instructions to send there could be a new power constraint. Not really sure how to solve this just yet.
        power_constraints = self.controller.get_power_constraint(
            current_timezone_time(), None
        )

        if power_constraints is None:
            raise ValueError("Power Constraints not set.")

        limit_range: PEBCAllowedLimitRange = power_constraints.allowed_limit_ranges[1]

        limit_ranges: Dict[CommodityQuantity, List[PEBCAllowedLimitRange]] = {}
        for limit_range in power_constraints.allowed_limit_ranges:
            if limit_range.commodity_quantity in limit_ranges:
                limit_ranges[limit_range.commodity_quantity].append(limit_range)
            else:
                limit_ranges[limit_range.commodity_quantity] = [limit_range]

        for commodity_quantity, ranges in limit_ranges.items():
            await self.generate_curtail_commodity_quantity_instruction_triggers(
                commodity_quantity=commodity_quantity,
                limit_ranges=ranges,
            )
