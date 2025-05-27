import asyncio

from connectivity.s2_channel import S2Channel

from testsuites.controllers.controller import Controller
from testsuites.test_logger import AbstractTestLogger
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
from connectivity.config import BaseTestConfig, NoSelectionRMTestConfig

import logging

logger = logging.getLogger(__name__)


class NoSelectionTestCase(S2TestCase):
    control_type = ProtocolControlType.NO_SELECTION

    name = "Test Receive RM Details"

    TIMEOUT = 5

    controller: BaseRMController
    config: BaseTestConfig


class NotControllableRMTestCase(S2TestCase):
    control_type = ProtocolControlType.NOT_CONTROLABLE

    controller: BaseRMController
    config: NoSelectionRMTestConfig
    name = "Not Controllable Control Tasks"

    TIMEOUT = 5

    async def setup(self):
        logger.info("WAITING FOR RM DETAILS")
        await self.controller._resource_manager_details_received.wait()
        logger.info("%s, %s", self.controller._resource_manager_details_received, self.controller.resource_manager_details)
        logger.info("RECEIVED RM DETAILS")

    def update_resource_manager_details_precondition(
        self, precondition_id: str | None = None
    ):
        """Tests the system description precondition.

        Args:
            precondition_id (string): The ID from the S2 Specification
        """
        self.assertIsNotNone(
            self.controller.resource_manager_details,
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update Resource Manager Details' not complete.",
        )
        self.test_logger.success(
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update Resource Manager Details' is complete."
        )

    @S2TestCase.test(name="9.2.5. Update Power Forecast")
    async def test_communicate_power_forecast(self):
        self.update_resource_manager_details_precondition("9.2.5.2.")

        message = await self.check_receive_message_type(PowerForecast)

    @S2TestCase.test(name="9.2.4. Communicate Power Measurement")
    async def test_receive_power_measurement(self):
        self.update_resource_manager_details_precondition("9.2.4.2.")

        message = await self.check_receive_message_type(PowerMeasurement)
