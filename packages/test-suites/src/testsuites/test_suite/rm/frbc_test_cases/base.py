import logging

from testsuites.certificate.certificate import (
    ComplianceReport,
)
from connectivity.config import FRBCRMTestConfig
from testsuites.controllers import FRBCRMController
from s2python.common import ControlType as ProtocolControlType
from ..base_test_case import NoSelectionTestCase
from testsuites.test_suite.test_suite import S2TestCase, TestLogger
from connectivity.s2_channel import S2Channel

logger = logging.getLogger(__name__)


class FRBCTestCase(NoSelectionTestCase):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL

    TIMEOUT = 5

    controller: FRBCRMController
    config: FRBCRMTestConfig

    def __init__(
        self,
        config: FRBCRMTestConfig,
        channel: S2Channel,
        controller: FRBCRMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

    async def setup(self):
        await self.controller._system_description_sent.wait()

    async def wait_for_system_description(self):
        system_description = self.controller.system_description
        if (
            system_description is None
            and not self.controller._system_description_sent.is_set()
        ):
            logger.debug(
                "Waiting. %s, %s",
                system_description,
                self.controller._system_description_sent,
            )
            await self.controller._system_description_sent.wait()
        logger.debug("System description is set.")
