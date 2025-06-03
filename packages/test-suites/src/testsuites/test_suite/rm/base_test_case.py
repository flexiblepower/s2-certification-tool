import asyncio

from connectivity.s2_channel import S2Channel

from testsuites.test_suite import NotApplicableTestException
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


class NotControllableRMTestCase(S2TestCase):
    control_type = ProtocolControlType.NOT_CONTROLABLE

    controller: BaseRMController
    config: NoSelectionRMTestConfig
    name = "Not Controllable Control Tasks"

    TIMEOUT = 5

    async def setup(self):
        await self.controller._resource_manager_details_received.wait()
        logger.info(
            "%s, %s",
            self.controller._resource_manager_details_received,
            self.controller.resource_manager_details,
        )

        self.message_handlers[PowerForecast] = self.handle_power_forecast
        self.message_handlers[PowerMeasurement] = self.handle_power_measurements

    async def handle_power_forecast(
        self, message: PowerForecast, channel: "S2Channel", send_okay
    ):
        await self.add_test_method(
            "9.2.5. Update Power Forecast", self.validate_power_forecast, message
        )
        await send_okay

    async def handle_power_measurements(
        self, message: PowerForecast, channel: "S2Channel", send_okay
    ):
        await self.add_test_method(
            "9.2.4. Communicate Power Measurement",
            self.validate_power_measurement,
            message,
        )
        await send_okay

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

    async def validate_power_forecast(self, message: PowerForecast):
        self.update_resource_manager_details_precondition("9.2.5.2.")

        # Sanity check
        self.assertIsNotNone(message)
        self.assertEqual(type(message), PowerForecast)

        if self.controller.resource_manager_details is None:
            raise AssertionError("Resource Manager details not set in controller!")

        self.assertFalse(
            self.controller.resource_manager_details.provides_forecast,
            "Received Power Forecast despite RM Details `provides_forecast` being false.",
        )

        for element in message.elements:
            for value in element.power_values:
                # TODO: Check if this is a valid check.
                # ! Unsure
                self.assertTrue(
                    value.commodity_quantity
                    not in self.controller.resource_manager_details.provides_power_measurement_types,
                    "Received forecast for commodity that isn't present in RM Details `provides_power_measurement_types`",
                )

    async def validate_power_measurement(self, message: PowerMeasurement):
        self.update_resource_manager_details_precondition("9.2.5.2.")

        # Sanity check
        self.assertIsNotNone(message)
        self.assertEqual(type(message), PowerMeasurement)

        if self.controller.resource_manager_details is None:
            raise AssertionError("Resource Manager details not set in controller!")

        for value in message.values:
            self.assertTrue(
                value.commodity_quantity
                not in self.controller.resource_manager_details.provides_power_measurement_types,
                "Received power measurement for commodity that isn't present in RM Details `provides_power_measurement_types`",
            )
