from ..certificate.certificate import (
    ComplianceFinding,
    ComplianceReport,
    ComplianceStatus,
)
from ..config import BaseTestConfig
from ..connection import BaseRMConnection
from ..controllers.controller import BaseController
from ..test_suite.test_suite import S2TestCase

from s2python.common import (
    PowerForecast,
    PowerMeasurement,
    ControlType as ProtocolControlType,
    ResourceManagerDetails,
)


class NoSelectionTestCase(S2TestCase):

    control_type = ProtocolControlType.NO_SELECTION

    TIMEOUT = 5

    controller: BaseController
    config: BaseTestConfig

    def __init__(
        self,
        config: BaseTestConfig,
        connection: BaseRMConnection,
        controller: BaseController,
        report: ComplianceReport,
    ):
        super().__init__(config, connection, controller, report)

    async def test_validate_rm_details_received(self):
        finding = ComplianceFinding(message_type=ResourceManagerDetails)

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

        finding = ComplianceFinding(message_type=PowerForecast)

        message = await self.check_receive_message_type(PowerForecast, finding)

        self.report.add_finding(finding)

    @S2TestCase.test
    async def test_receive_power_measurement(self):
        finding = ComplianceFinding(message_type=PowerMeasurement)

        message = await self.check_receive_message_type(PowerMeasurement, finding)

        self.report.add_finding(finding)
