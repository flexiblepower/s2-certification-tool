import logging
from typing import Optional

from testsuites.certificate.certificate import (
    ComplianceFinding,
    ComplianceParameter,
    ComplianceReport,
    ComplianceStatus,
)
from connectivity.config import PEBCTestConfig
from testsuites.controllers.pebc_controller import PEBCController
from s2python.common import ControlType as ProtocolControlType
from testsuites.test_suite.base_test_case import NoSelectionTestCase
from connectivity.s2_channel import S2Channel

logger = logging.getLogger(__name__)


class PEBCTestCase(NoSelectionTestCase):
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL
    controller: PEBCController
    config: PEBCTestConfig

    def __init__(
        self,
        config: PEBCTestConfig,
        channel: S2Channel,
        controller: PEBCController,
        report: ComplianceReport,
        logger: logging.Logger = logging.getLogger(__name__),
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
