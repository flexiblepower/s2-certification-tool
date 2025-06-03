import logging
from typing import Dict, List, Tuple

from testsuites.certificate.certificate import (
    ComplianceReport,
)
from connectivity.config import PEBCRMTestConfig
from connectivity.s2_channel import S2Channel
from testsuites.controllers import PEBCRMController

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
)
from s2python.pebc import (
    PEBCAllowedLimitRange,
    PEBCPowerConstraints,
    PEBCPowerEnvelope,
    PEBCPowerEnvelopeElement,
    PEBCPowerEnvelopeLimitType,
    PEBCEnergyConstraint,
)

from itertools import product

logger = logging.getLogger(__name__)


class PEBCTestCase(S2TestCase):
    name = "9.3. Power Envelope Based Control Tasks"
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL
    controller: PEBCRMController
    config: PEBCRMTestConfig

    def __init__(
        self,
        config: PEBCRMTestConfig,
        channel: S2Channel,
        controller: PEBCRMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

    async def setup(self):
        await self.controller._power_constraints_received.wait()

    async def generate_tests(self):
        await super().generate_tests()

        await self.add_test_method(
            "9.3.1. Update Power Constraints", self.validate_power_constraints_set
        )
        await self.add_test_method(
            "9.3.3. Update Energy Constraints", self.validate_energy_constraints_set
        )

        await self.generate_set_limit_range_instruction_tests()

        # await self.add_test_method(
        #     "9.3.4. Revoke Energy Constraints", self.test_revoke_power_constraints
        # )

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

    async def wait_until_power_constraints_set(self):
        power_constraints = self.controller.power_constraints
        if (
            power_constraints is None
            and not self.controller._power_constraints_received.is_set()
        ):
            logger.info(
                "Waiting. %s, %s",
                power_constraints,
                self.controller._power_constraints_received,
            )
            await self.controller._power_constraints_received.wait()
            logger.info("Power Constraints is set.")

    async def validate_power_constraints_set(self):
        await self.control_type_set_pebc_precondition("9.3.1.2.")
        await self.wait_until_power_constraints_set()

    async def validate_energy_constraints_set(self):
        if not self.config.sends_energy_constraints:
            raise NotApplicableTestException(
                "This device does not send Energy Constraints messages."
            )

        await self.control_type_set_pebc_precondition("9.3.3.2.")

        message = await self.controller.message_awaiter.wait_for_message(
            PEBCEnergyConstraint, self.TIMEOUT
        )

        # TODO Add check for precondition that energy constraints are within power constraints limits

    def create_power_envelope(
        self, commodity_quantity, lower_limit, upper_limit, duration=3600
    ) -> PEBCPowerEnvelope:
        return PEBCPowerEnvelope(
            id="test_env",  # type: ignore
            commodity_quantity=commodity_quantity,
            power_envelope_elements=[
                PEBCPowerEnvelopeElement(
                    lower_limit=lower_limit,
                    upper_limit=upper_limit,
                    duration=duration,  # type: ignore
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

        power_envelope = self.create_power_envelope(
            commodity_quantity=commodity_quantity,
            lower_limit=lower_limit,
            upper_limit=upper_limit,
            duration=duration,
        )
        # Prepare coroutines first so the events are waiting in the awaiter.
        # This avoids the case where the message somehow arrives between sending the message and starting to await.
        # This is highly unlikely but might as well make sure!
        # power_measurement_coroutine = self.controller.message_awaiter.wait_for_message(
        #     PowerMeasurement, 60
        # )
        status_update_coroutine = self.controller.message_awaiter.wait_for_message(
            InstructionStatusUpdate, 10
        )

        instruction = await self.controller.send_power_envelope_instruction(
            self.channel, [power_envelope]
        )

        status_update = await status_update_coroutine

        self.assertEqual(type(status_update), InstructionStatusUpdate)
        if type(status_update) != InstructionStatusUpdate:
            return

        self.assertEqual(status_update.instruction_id, instruction.id)

        self.assertEqual(status_update.status_type, expected_instruction_status)

        # TODO: Revoke instruction
        # await self.controller.send_revoke_power_envelope_instruction(
        #     self.channel,
        # )

    async def generate_curtail_commodity_quantity_tests(
        self,
        power_constraints: PEBCPowerConstraints,
        commodity_quantity: CommodityQuantity,
        limit_ranges: List[PEBCAllowedLimitRange],
        duration=3600,
    ):
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

        for lower_limit, upper_limit in limit_range_pairs:
            limits = [
                (lower_limit.start_of_range, upper_limit.start_of_range),
                (lower_limit.start_of_range, upper_limit.end_of_range),
                (lower_limit.end_of_range, upper_limit.start_of_range),
                (lower_limit.end_of_range, upper_limit.end_of_range),
            ]
            for upper, lower in limits:

                await self.add_test_method(
                    f"Succeed Curtail {commodity_quantity}",
                    self.send_power_envelope,
                    commodity_quantity=commodity_quantity,
                    lower_limit=lower,
                    upper_limit=upper,
                    duration=duration,
                    expected_instruction_status=InstructionStatus.SUCCEEDED,
                    fail_result_status=TestResultStatus.FAIL,
                )

                await self.add_test_method(
                    f"Reject Curtail {commodity_quantity}",
                    self.send_power_envelope,
                    commodity_quantity=commodity_quantity,
                    lower_limit=lower_limit.end_of_range - 1,
                    upper_limit=upper_limit.start_of_range + 1,
                    duration=duration,
                    expected_instruction_status=InstructionStatus.REJECTED,
                    fail_result_status=TestResultStatus.FAIL,
                )

    async def generate_set_limit_range_instruction_tests(self):
        await self.wait_until_power_constraints_set()

        power_constraints = self.controller.power_constraints

        if power_constraints is None:
            raise ValueError("Power Constraints not set.")

        limit_range: PEBCAllowedLimitRange = power_constraints.allowed_limit_ranges[1]

        limit_ranges: Dict[CommodityQuantity, List[PEBCAllowedLimitRange]] = {}
        for limit_range in power_constraints.allowed_limit_ranges:
            if limit_range.commodity_quantity in limit_ranges:
                limit_ranges[limit_range.commodity_quantity].append(limit_range)
            else:
                limit_ranges[limit_range.commodity_quantity] = [limit_range]

        statuses: List[TestResultStatus] = []
        for commodity_quantity, ranges in limit_ranges.items():
            await self.generate_curtail_commodity_quantity_tests(
                power_constraints=power_constraints,
                commodity_quantity=commodity_quantity,
                limit_ranges=ranges,
            )

        self.test_logger.log_status_list(
            "Curtailment Instruction Test Complete.", statuses, ident=0
        )
