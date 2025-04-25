from certificate.certificate import ComplianceFinding, ComplianceReport
from config import BaseTestConfig
from connection import Connection
from controllers.controller import BaseController
from test_suite.test_suite import S2TestCase

from s2python.common import (
    PowerForecast,
    PowerMeasurement,
    ControlType as ProtocolControlType,
)


class NoSelectionTestCase(S2TestCase):

    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL

    TIMEOUT = 5

    controller: BaseController
    config: BaseTestConfig

    def __init__(
        self,
        config: BaseTestConfig,
        connection: Connection,
        controller: BaseController,
        report: ComplianceReport,
    ):
        super().__init__(config, connection, controller, report)

    @S2TestCase.test_case
    async def test_receive_power_forecast(self):

        finding = ComplianceFinding(message_type=PowerForecast)

        message = await self.check_receive_message_type(PowerForecast, finding)

        self.report.add_finding(finding)

    @S2TestCase.test_case
    async def test_receive_power_measurement(self):
        finding = ComplianceFinding(message_type=PowerMeasurement)

        message = await self.check_receive_message_type(PowerMeasurement, finding)

        self.report.add_finding(finding)
