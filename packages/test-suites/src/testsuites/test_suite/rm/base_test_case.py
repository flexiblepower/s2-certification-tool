from ...certificate.certificate import (
    TestSuiteResults,
    ComplianceReport,
    TestResultStatus,
)
from testsuites.controllers import BaseRMController
from testsuites.test_suite.test_suite import S2TestCase, TestLogger

from s2python.common import (
    PowerForecast,
    PowerMeasurement,
    ControlType as ProtocolControlType,
)
from connectivity.config import BaseTestConfig

import logging

logger = logging.getLogger(__name__)


class NoSelectionTestCase(S2TestCase):
    control_type = ProtocolControlType.NO_SELECTION

    name = "Test Receive RM Details"

    TIMEOUT = 5

    controller: BaseRMController
    config: BaseTestConfig


class UpdateResourceManagerDetailsTestCase(NoSelectionTestCase):
    name = "9.2.1. Update Resource Manager Details"

    async def test_validate_rm_details_received(self):

        self.assertIsNotNone(self.controller.resource_manager_details)

        self.test_logger.success("Resource manager details received.")


class ReceivePowerForecastTestCase(NoSelectionTestCase):
    name = "Test Receive Power Forecast"

    @S2TestCase.test("Test Receive Power Forecast")
    async def test_receive_power_forecast(self):
        message = await self.check_receive_message_type(PowerForecast)

        self.test_logger.success("Test Received Power Forecast")


class ReceivePowerMeasurementTestCase(NoSelectionTestCase):
    name = "Test Receive Power Measurement"

    @S2TestCase.test("Test Receive Power Measurement")
    async def test_receive_power_measurement(self):
        message = await self.check_receive_message_type(PowerMeasurement)
        self.test_logger.success("Test Received Power Measurement")
