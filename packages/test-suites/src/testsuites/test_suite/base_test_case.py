from ..certificate.certificate import (
    ComplianceFinding,
    ComplianceReport,
    ComplianceStatus,
)
from ..controllers.controller import BaseController
from ..test_suite.test_suite import S2TestCase

from s2python.common import (
    PowerForecast,
    PowerMeasurement,
    ControlType as ProtocolControlType,
    ResourceManagerDetails,
)
from connectivity.config import BaseTestConfig
from connectivity.s2_channel import S2Channel


class NoSelectionTestCase(S2TestCase):

    control_type = ProtocolControlType.NO_SELECTION

    TIMEOUT = 5

    controller: BaseController
    config: BaseTestConfig

    def __init__(
        self,
        config: BaseTestConfig,
        channel: S2Channel,
        controller: BaseController,
        report: ComplianceReport,
    ):
        super().__init__(config, channel, controller, report)

    async def test_validate_rm_details_received(self):
        finding = ComplianceFinding(test="Test Receive RM Details")

        if self.controller.resource_manager_details is not None:
            finding.add_parameter(
                "ResourceManagerDetails Received.", ComplianceStatus.PASS
            )
            finding.add_parameter(
                "ResourceManagerDetails Valid.", ComplianceStatus.PASS
            )

        self.report.add_finding(finding)

    @S2TestCase.test
    async def test_receive_power_forecast(self):

        finding = ComplianceFinding(test="Test Receive Power Forecast")

        message = await self.check_receive_message_type(PowerForecast, finding)

        self.report.add_finding(finding)

    @S2TestCase.test
    async def test_receive_power_measurement(self):
        finding = ComplianceFinding(test="Test Receive Power Measurement")

        message = await self.check_receive_message_type(PowerMeasurement, finding)

        self.report.add_finding(finding)
