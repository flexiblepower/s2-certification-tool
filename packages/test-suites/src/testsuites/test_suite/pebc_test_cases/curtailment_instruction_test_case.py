import datetime
from enum import Enum
import json
import logging
from typing import Dict, List, Tuple
import uuid

from testsuites.test_suite.test_suite import TestLogger
from testsuites.certificate.certificate import (
    TestSuiteResults,
    TestResult,
    ComplianceReport,
    TestResultStatus,
)
from connectivity.config import BaseTestConfig, PEBCRMTestConfig
from testsuites.controllers.controller import Controller
from testsuites.controllers import PEBCRMController
from s2python.common import (
    ControlType as ProtocolControlType,
    PowerMeasurement,
    InstructionStatusUpdate,
    CommodityQuantity,
    NumberRange,
    InstructionStatus,
)
from s2python.pebc import (
    PEBCAllowedLimitRange,
    PEBCInstruction,
    PEBCPowerConstraints,
    PEBCPowerEnvelope,
    PEBCPowerEnvelopeElement,
    PEBCPowerEnvelopeLimitType,
)
from testsuites.test_suite.base_test_case import NoSelectionTestCase
from testsuites.test_suite.test_suite import S2TestCase
from connectivity.s2_channel import S2Channel
from .base import PEBCTestCase

from itertools import product

logger = logging.getLogger(__name__)


class PEBCCurtailmentInstructionTestCase(PEBCTestCase):
    name = "Test sending curtailment instruction."

    async def generate_tests(self):
        await super().generate_tests()
        await self.generate_set_limit_range_instruction_tests()

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

        logger.info("Instruction sent")

        status_update = await status_update_coroutine

        self.assertEqual(type(status_update), InstructionStatusUpdate)
        if type(status_update) != InstructionStatusUpdate:
            return

        self.assertEqual(status_update.instruction_id, instruction.id)
        # logger.info("Status Update: %s", status_update)
        # # TODO: THis could break if multiple status updates are incoming...
        # if status_update.instruction_id != instruction.id:

        #     self.test_logger.soft_error(
        #         "Curtailment Test {power_envelope.commodity_quantity}: InstructionStatusUpdate instruction_id does not matches instruction's ID."
        #     )
        #     return TestResultStatus.SOFT_FAIL

        self.assertEqual(status_update.status_type, expected_instruction_status)
        # if status_update.status_type != expected_instruction_status:
        #     self.test_logger.soft_error(
        #         f"Curtailment Test {power_envelope.commodity_quantity}: Expected Instruction Status of {expected_instruction_status} but received {status_update.status_type}."
        #     )
        #     return TestResultStatus.SOFT_FAIL
        # return TestResultStatus.PASS

    # async def curtail_with_limits(
    #     self,
    #     commodity_quantity: CommodityQuantity,
    #     lower_limit: NumberRange,
    #     upper_limit: NumberRange,
    #     duration: int,
    # ) -> list[TestResultStatus]:
    #     limits = [
    #         (lower_limit.start_of_range, upper_limit.start_of_range),
    #         (lower_limit.start_of_range, upper_limit.end_of_range),
    #         (lower_limit.end_of_range, upper_limit.start_of_range),
    #         (lower_limit.end_of_range, upper_limit.end_of_range),
    #     ]

    #     for upper, lower in limits:
    #         power_envelope = self.create_power_envelope(
    #             commodity_quantity=commodity_quantity,
    #             lower_limit=lower,
    #             upper_limit=upper,
    #             duration=duration,
    #         )
    #         logger.debug("Curtailing with power envelope: %s", power_envelope)

    #         self.test_logger.info(
    #             f"Curtailing {power_envelope.commodity_quantity} with upper_limit={upper}, lower_limit={lower}"
    #         )

    #         status = await self.send_power_envelope(
    #             power_envelope, InstructionStatus.SUCCEEDED
    #         )
    #         statuses.append(status)

    #         power_envelope = self.create_power_envelope(
    #             commodity_quantity=commodity_quantity,
    #             lower_limit=lower_limit.end_of_range - 1,
    #             upper_limit=upper_limit.start_of_range + 1,
    #             duration=duration,
    #         )

    #         status = await self.send_power_envelope(
    #             power_envelope, InstructionStatus.REJECTED
    #         )
    #         statuses.append(status)

    #     return statuses

    def generate_curtail_commodity_quantity_tests(
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

        logger.info("---------- Generating ----------")
        logger.info(limit_range_pairs)
        for lower_limit, upper_limit in limit_range_pairs:
            limits = [
                (lower_limit.start_of_range, upper_limit.start_of_range),
                (lower_limit.start_of_range, upper_limit.end_of_range),
                (lower_limit.end_of_range, upper_limit.start_of_range),
                (lower_limit.end_of_range, upper_limit.end_of_range),
            ]
            for upper, lower in limits:

                self.add_test_method(
                    f"Succeed Curtail {commodity_quantity}",
                    self.send_power_envelope,
                    commodity_quantity=commodity_quantity,
                    lower_limit=lower,
                    upper_limit=upper,
                    duration=duration,
                    expected_instruction_status=InstructionStatus.SUCCEEDED,
                    fail_result_status=TestResultStatus.SOFT_FAIL
                )

                self.add_test_method(
                    f"Reject Curtail {commodity_quantity}",
                    self.send_power_envelope,
                    commodity_quantity=commodity_quantity,
                    lower_limit=lower_limit.end_of_range - 1,
                    upper_limit=upper_limit.start_of_range + 1,
                    duration=duration,
                    expected_instruction_status=InstructionStatus.REJECTED,
                    fail_result_status=TestResultStatus.SOFT_FAIL
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
            self.generate_curtail_commodity_quantity_tests(
                power_constraints=power_constraints,
                commodity_quantity=commodity_quantity,
                limit_ranges=ranges,
            )

        self.test_logger.log_status_list(
            "Curtailment Instruction Test Complete.", statuses, ident=0
        )

        # if TestResultStatus.FAIL in statuses:
        #     self.name.status = TestResultStatus.FAIL
        # elif TestResultStatus.SOFT_FAIL in statuses:
        #     self.name.status = TestResultStatus.SOFT_FAIL
        # elif TestResultStatus.PASS in statuses:
        #     self.name.status = TestResultStatus.PASS

        # return TestResultStatus.PASS, None
