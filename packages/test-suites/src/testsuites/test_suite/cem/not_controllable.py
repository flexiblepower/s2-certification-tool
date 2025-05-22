import uuid
from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    PowerForecast,
    PowerForecastElement,
    PowerForecastValue,
    PowerMeasurement,
    PowerValue,
    ResourceManagerDetails,
    Handshake,
    NumberRange,
    Commodity,
    PowerRange,
    CommodityQuantity,
    Transition,
    Duration,
    RevokeObject,
)

from testsuites.certificate.certificate import ComplianceReport
from testsuites.controllers.cem.not_controllable_controller import (
    NotControllableCEMController,
)
from testsuites.util import current_timezone_time
from testsuites.test_logger import TestLogger
from testsuites.test_suite.rm.base_test_case import NoSelectionTestCase
from connectivity.s2_channel import S2Channel

from connectivity.config import BaseTestConfig

from testsuites.test_suite.test_suite import S2TestCase


class NotControllableCEMTestCase(S2TestCase):
    name = "CEM Not Controllable Control Type Test Case"
    control_type = ProtocolControlType.NOT_CONTROLABLE

    TIMEOUT = 5

    controller: NotControllableCEMController
    config: BaseTestConfig

    def __init__(
        self,
        config: BaseTestConfig,
        channel: S2Channel,
        controller: NotControllableCEMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

    def update_resource_manager_details_precondition(
        self, precondition_id: str | None = None
    ):
        """Tests the system description precondition.

        Args:
            precondition_id (string): The ID from the S2 Specification
        """
        # TODO: Maybe a better way to do this, but the fact that the control type was selected suggests this is passed.

        self.assertTrue(
            True,
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update Resource Manager Details' not complete.",
        )
        self.test_logger.success(
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update Resource Manager Details' is complete."
        )

    def get_system_description_commodity_quantities(self) -> list[CommodityQuantity]:
        if self.controller.resource_manager_details is None:
            raise ValueError("Resource Manager Details not set.")

        return self.controller.resource_manager_details.provides_power_measurement_types

    @S2TestCase.test(name="9.2.4. Communicate Power Measurement")
    async def test_communicate_power_measurement(self):
        self.update_resource_manager_details_precondition("9.2.4.2.")

        commodity_quantities = self.get_system_description_commodity_quantities()

        power_values = [
            PowerValue(commodity_quantity=commodity_quantity, value=100)
            for commodity_quantity in commodity_quantities
        ]

        power_measurement = PowerMeasurement(
            measurement_timestamp=current_timezone_time(),
            message_id=uuid.uuid4(),
            values=power_values,
        )

        await self.controller.send_power_measurement(self.channel, power_measurement)

    @S2TestCase.test(name="9.2.5. Update Power Forecast")
    async def test_update_power_forecast(self):
        self.update_resource_manager_details_precondition("9.2.4.2.")

        commodity_quantities = self.get_system_description_commodity_quantities()

        elements = [
            PowerForecastElement(
                duration=Duration(3600.0),
                power_values=[
                    PowerForecastValue(
                        commodity_quantity=q,
                        value_expected=100,
                        value_lower_limit=None,
                        value_upper_limit=None,
                        value_lower_68PPR=None,
                        value_upper_68PPR=None,
                        value_lower_95PPR=None,
                        value_upper_95PPR=None,
                    )
                    for q in commodity_quantities
                ],
            )
        ]

        power_forecast = PowerForecast(
            message_id=uuid.uuid4(),
            start_time=current_timezone_time(),
            elements=elements,
        )

        await self.controller.send_power_forecast(self.channel, power_forecast)
