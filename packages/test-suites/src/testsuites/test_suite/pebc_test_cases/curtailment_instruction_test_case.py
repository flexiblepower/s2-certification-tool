import datetime
from enum import Enum
import json
import logging
from typing import Dict, List, Tuple
import uuid

from testsuites.certificate.certificate import (
    ComplianceFinding,
    ComplianceParameter,
    ComplianceReport,
    ComplianceStatus,
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
    finding = ComplianceFinding(test="Test sending curtailment instruction.")

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
        power_envelope: PEBCPowerEnvelope,
        expected_instruction_status: InstructionStatus,
    ) -> ComplianceStatus:
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

        if type(status_update) != InstructionStatusUpdate:
            self.test_logger.error(
                f"Curtailment Test {power_envelope.commodity_quantity}: No Instruction status received after sending curtailment for {status_update}."
            )
            return ComplianceStatus.FAIL

        logger.info("Status Update: %s", status_update)
        # TODO: THis could break if multiple status updates are incoming...
        if status_update.instruction_id != instruction.id:

            self.test_logger.soft_error(
                "Curtailment Test {power_envelope.commodity_quantity}: InstructionStatusUpdate instruction_id does not matches instruction's ID."
            )
            return ComplianceStatus.SOFT_FAIL

        if status_update.status_type != expected_instruction_status:
            self.test_logger.soft_error(
                f"Curtailment Test {power_envelope.commodity_quantity}: Expected Instruction Status of {expected_instruction_status} but received {status_update.status_type}."
            )
            return ComplianceStatus.SOFT_FAIL
        return ComplianceStatus.PASS

    async def curtail_with_limits(
        self,
        commodity_quantity: CommodityQuantity,
        lower_limit: NumberRange,
        upper_limit: NumberRange,
        duration: int,
    ) -> list[ComplianceStatus]:
        limits = [
            (lower_limit.start_of_range, upper_limit.start_of_range),
            (lower_limit.start_of_range, upper_limit.end_of_range),
            (lower_limit.end_of_range, upper_limit.start_of_range),
            (lower_limit.end_of_range, upper_limit.end_of_range),
        ]

        statuses = []
        for upper, lower in limits:
            power_envelope = self.create_power_envelope(
                commodity_quantity=commodity_quantity,
                lower_limit=lower,
                upper_limit=upper,
                duration=duration,
            )
            logger.debug("Curtailing with power envelope: %s", power_envelope)

            self.test_logger.info(
                f"Curtailing {power_envelope.commodity_quantity} with upper_limit={upper}, lower_limit={lower}"
            )

            status = await self.send_power_envelope(
                power_envelope, InstructionStatus.SUCCEEDED
            )
            statuses.append(status)

            power_envelope = self.create_power_envelope(
                commodity_quantity=commodity_quantity,
                lower_limit=lower_limit.end_of_range - 1,
                upper_limit=upper_limit.start_of_range + 1,
                duration=duration,
            )

            status = await self.send_power_envelope(
                power_envelope, InstructionStatus.REJECTED
            )
            statuses.append(status)

        return statuses

    async def curtail_commodity_quantity(
        self,
        power_constraints: PEBCPowerConstraints,
        commodity_quantity: CommodityQuantity,
        limits: List[PEBCAllowedLimitRange],
        duration=3600,
    ) -> list[ComplianceStatus]:
        logger.info("Curtailing %s", commodity_quantity)

        lower_limits: List[NumberRange] = []
        upper_limits: List[NumberRange] = []

        for limit in limits:
            if limit.limit_type == PEBCPowerEnvelopeLimitType.LOWER_LIMIT:
                lower_limits.append(limit.range_boundary)
            else:
                upper_limits.append(limit.range_boundary)

        limit_range_pairs: List[Tuple[NumberRange, NumberRange]] = list(
            product(lower_limits, upper_limits)
        )
        logger.info(limit_range_pairs)

        statuses = []
        for lower_limit, upper_limit in limit_range_pairs:
            statuses += await self.curtail_with_limits(
                commodity_quantity, lower_limit, upper_limit, duration
            )

        return statuses

    @S2TestCase.test
    async def test_set_limit_ranges_instruction(self):
        logger.info("Testing set limit range")
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

        statuses: List[ComplianceStatus] = []
        for commodity_quantity, ranges in limit_ranges.items():
            statuses += await self.curtail_commodity_quantity(
                power_constraints=power_constraints,
                commodity_quantity=commodity_quantity,
                limits=ranges,
            )
        self.test_logger.log_status_list(
            "Curtailment Instruction Test Complete.", statuses, ident=0
        )

        if ComplianceStatus.FAIL in statuses:
            self.finding.status = ComplianceStatus.FAIL
        elif ComplianceStatus.SOFT_FAIL in statuses:
            self.finding.status = ComplianceStatus.SOFT_FAIL
        elif ComplianceStatus.PASS in statuses:
            self.finding.status = ComplianceStatus.PASS
