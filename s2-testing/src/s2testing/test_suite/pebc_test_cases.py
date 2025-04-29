import datetime
import logging
import uuid

from s2testing.certificate.certificate import (
    ComplianceFinding,
    ComplianceParameter,
    ComplianceReport,
    ComplianceStatus,
)
from s2testing.config import BaseTestConfig, PEBCTestConfig
from s2testing.connection import BaseRMConnection
from s2testing.controllers.controller import Controller
from s2testing.controllers.pebc_controller import PEBCController
from s2python.common import (
    ControlType as ProtocolControlType,
    PowerMeasurement,
)
from s2python.pebc import (
    PEBCAllowedLimitRange,
    PEBCInstruction,
    PEBCPowerConstraints,
    PEBCPowerEnvelope,
    PEBCPowerEnvelopeElement,
)
from s2testing.test_suite.base_test_case import NoSelectionTestCase
from s2testing.test_suite.test_suite import S2TestCase

logger = logging.getLogger(__name__)


class PEBCTestCase(NoSelectionTestCase):
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL
    controller: PEBCController
    config: PEBCTestConfig

    def __init__(
        self,
        config: PEBCTestConfig,
        connection: BaseRMConnection,
        controller: PEBCController,
        report: ComplianceReport,
    ):
        super().__init__(config, connection, controller, report)

    async def setup(self):
        await self.controller._power_constraints_received.wait()

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

    @S2TestCase.test
    async def validate_power_constraints_set(self):
        await self.wait_until_power_constraints_set()

        finding = ComplianceFinding(message_type=PEBCPowerConstraints)
        finding.add_parameter(
            param=ComplianceParameter(
                name="PEBCPowerConstraints Provided.", status=ComplianceStatus.PASS
            )
        )

        self.report.add_finding(finding)

    # async def test_set_limit_ranges_instruction(self):
    #     # for limit_ranges in self.power_constraints.allowed_limit_ranges:
    #     logger.info("Testing set limit range")
    #     await self.wait_until_power_constraints_set()

    #     power_constraints = self.controller.power_constraints

    #     if power_constraints is None:
    #         raise ValueError("Power Constraints not set.")

    #     limit_range: PEBCAllowedLimitRange = power_constraints.allowed_limit_ranges[1]
    #     logger.info(power_constraints)
    #     logger.info("Sending Instruction.")

    #     # exec_time = datetime.datetime.now()
    #     exec_time = datetime.datetime.fromisoformat("2025-04-22T09:30:00+00:00")
    #     # logger.info(exec_time.replace(tzinfo=datetime.timezone.utc))
    #     logger.info(exec_time)

    #     instruction = PEBCInstruction(
    #         message_id=uuid.uuid4(),
    #         id=power_constraints.id,
    #         power_constraints_id=power_constraints.id,
    #         power_envelopes=[
    #             PEBCPowerEnvelope(
    #                 id="pe_test",  # type: ignore
    #                 commodity_quantity=limit_range.commodity_quantity,
    #                 power_envelope_elements=[
    #                     PEBCPowerEnvelopeElement(
    #                         lower_limit=-2000.00,
    #                         upper_limit=0,
    #                         duration=3600000,  # type: ignore
    #                     )
    #                 ],
    #             )
    #         ],
    #         # Make it timezone-aware (UTC)
    #         execution_time=exec_time.replace(tzinfo=datetime.timezone.utc),
    #         abnormal_condition=False,
    #     )
    #     logger.info(instruction)
    #     await self.connection.send_msg_and_await_reception_status(
    #         instruction, raise_on_error=True
    #     )
    #     logger.info("Instruction sent")

    # async def test_receives_interval_power_readings(self):

    #     if self.config is None or self.config.status_update_frequency is None:
    #         raise ValueError("Status Update Frequency required to test status updates.")

    #     logger.info("Waiting for power reading.")
    #     try:
    #         await self.controller.message_awaiter.wait_for_message(
    #             PowerMeasurement,
    #             timeout=float(self.config.status_update_frequency),
    #         )
    #         logger.info("Power reading received.")
    #         await self.controller.message_awaiter.wait_for_message(
    #             PowerMeasurement,
    #             timeout=float(
    #                 self.config.status_update_frequency
    #                 + self.config.status_update_frequency_buffer
    #             ),
    #         )
    #         logger.info("Power readings test passed.")
    #     except Exception:
    #         logger.exception("Did not receive power reading within allowed window.")
