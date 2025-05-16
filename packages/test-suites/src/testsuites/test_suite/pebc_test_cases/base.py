import logging
from typing import Optional

from testsuites.test_suite.test_suite import S2TestCase, TestLogger
from testsuites.certificate.certificate import (
    TestSuiteResults,
    TestResult,
    ComplianceReport,
    TestResultStatus,
)
from connectivity.config import PEBCRMTestConfig
from testsuites.controllers import PEBCRMController
from s2python.common import ControlType as ProtocolControlType
from testsuites.test_suite.base_test_case import NoSelectionTestCase
from connectivity.s2_channel import S2Channel

logger = logging.getLogger(__name__)


class PEBCTestCase(S2TestCase):
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
