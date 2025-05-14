from ..certificate.certificate import (
    ComplianceFinding,
    ComplianceReport,
    ComplianceStatus,
)
from ..controllers.controller import BaseController
from ..test_suite.test_suite import S2TestCase, TestLogger

from s2python.common import (
    PowerForecast,
    PowerMeasurement,
    ControlType as ProtocolControlType,
)
from connectivity.config import BaseTestConfig
from connectivity.s2_channel import S2Channel

import logging

logger = logging.getLogger(__name__)


class NoSelectionTestCase(S2TestCase):
    control_type = ProtocolControlType.NO_SELECTION

    finding = ComplianceFinding(test="Test Receive RM Details")

    TIMEOUT = 5

    controller: BaseController
    config: BaseTestConfig

    def __init__(
        self,
        config: BaseTestConfig,
        channel: S2Channel,
        controller: BaseController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

    async def test_validate_rm_details_received(self):
        if self.controller.resource_manager_details is not None:
            self.finding.add_parameter(
                "ResourceManagerDetails Received.", ComplianceStatus.PASS
            )
            self.finding.add_parameter(
                "ResourceManagerDetails Valid.", ComplianceStatus.PASS
            )

        self.test_logger.success("Resource manager details received.")


class ReceivePowerForecastTestCase(NoSelectionTestCase):
    finding = ComplianceFinding(test="Test Receive Power Forecast")

    @S2TestCase.test
    async def test_receive_power_forecast(self):
        message = await self.check_receive_message_type(PowerForecast)

        self.test_logger.success("Test Received Power Forecast")


class ReceivePowerMeasurementTestCase(NoSelectionTestCase):
    finding = ComplianceFinding(test="Test Receive Power Measurement")

    @S2TestCase.test
    async def test_receive_power_measurement(self):
        message = await self.check_receive_message_type(PowerMeasurement)
        self.test_logger.success("Test Received Power Measurement")
