import datetime
import logging
from typing import Dict, List
import uuid

from testsuites.certificate.certificate import (
    ComplianceFinding,
    ComplianceParameter,
    ComplianceReport,
    ComplianceStatus,
)
from connectivity.config import BaseTestConfig, PEBCTestConfig
from testsuites.controllers.controller import Controller
from testsuites.controllers.pebc_controller import PEBCController
from s2python.common import (
    ControlType as ProtocolControlType,
    PowerMeasurement,
    InstructionStatusUpdate,
    CommodityQuantity,
)
from s2python.pebc import (
    PEBCAllowedLimitRange,
    PEBCInstruction,
    PEBCPowerConstraints,
    PEBCPowerEnvelope,
    PEBCPowerEnvelopeElement,
)
from testsuites.test_suite.base_test_case import NoSelectionTestCase
from testsuites.test_suite.test_suite import S2TestCase
from connectivity.s2_channel import S2Channel
from .base import PEBCTestCase

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

    async def curtail_commodity_quantity(
        self,
        power_constraints: PEBCPowerConstraints,
        commodity_quantity: CommodityQuantity,
        limits: List[PEBCAllowedLimitRange],
        duration=3600,
    ):
        logger.info("Curtailing %s", commodity_quantity)

        power_envelopes = [
            self.create_power_envelope(
                commodity_quantity=commodity_quantity,
                lower_limit=-200,
                upper_limit=0,
                duration=duration,
            )
        ]

        # Prepare coroutines first so the events are waiting in the awaiter.
        # This avoids the case where the message somehow arrives between sending the message and starting to await.
        # This is highly unlikely but might as well make sure!
        power_measurement_coroutine = self.controller.message_awaiter.wait_for_message(
            PowerMeasurement, 60
        )
        status_update_coroutine = self.controller.message_awaiter.wait_for_message(
            InstructionStatusUpdate, 10
        )

        instruction = await self.controller.send_power_envelope_instruction(
            self.channel, power_envelopes
        )

        logger.info("Instruction sent")

        status_update = await status_update_coroutine

        if type(status_update) != InstructionStatusUpdate:
            self.add_finding_param(
                name="InstructionStatusUpdate received.", status=ComplianceStatus.FAIL
            )
            return
        self.add_finding_param(
            name="InstructionStatusUpdate received.", status=ComplianceStatus.PASS
        )

        logger.info("Status Update: %s", status_update)
        if status_update.instruction_id == instruction.id:
            self.add_finding_param(
                name="InstructionStatusUpdate instruction_id matches instruction's ID.",
                status=ComplianceStatus.PASS,
            )
        else:
            self.add_finding_param(
                name="InstructionStatusUpdate instruction_id matches instruction's ID.",
                status=ComplianceStatus.FAIL,
            )

        message = await power_measurement_coroutine

        logger.info("Received Power Measurement: %s", message)

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

        for commodity_quantity, ranges in limit_ranges.items():
            await self.curtail_commodity_quantity(
                power_constraints=power_constraints,
                commodity_quantity=commodity_quantity,
                limits=ranges,
            )
