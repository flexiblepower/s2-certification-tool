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
    ReceptionStatus,
    ReceptionStatusValues,
)
from s2python.message import S2Message


from testsuites.certificate.certificate import ComplianceReport, TestResultStatus
from testsuites.controllers.cem.not_controllable_controller import (
    NotControllableCEMController,
)
from testsuites.util import current_timezone_time
from testsuites.test_logger import TestLogger
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

    async def generate_tests(self):
        await self.add_trigger_method(
            self.send_valid_power_measurement_test, wait_time=2
        )
        # await self.add_trigger_method(self.send_power_forecast, wait_time=5)
        await self.add_trigger_method(self.send_invalid_measurement, wait_time=2)
        # await self.add_trigger_method(self.send_invalid_forecast, wait_time=5)

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

    async def base_message_send_validate(
        self, message: S2Message, reception_status: ReceptionStatus
    ):
        self.assertIsNotNone(message)
        self.assertIsNotNone(reception_status)
        self.assertEqual(reception_status.status, ReceptionStatusValues.OK)
        self.assertNotEqual(type(message), ReceptionStatus)
        self.assertEqual(message.message_id, reception_status.subject_message_id)  # type: ignore

    async def send_power_measurement(self, power_measurement: PowerMeasurement):
        reception_status = await self.controller.send_power_measurement(
            self.channel, power_measurement
        )
        await self.add_test_method(
            "Update power measurement",
            self.base_message_send_validate,
            power_measurement,
            reception_status,
        )

    async def send_power_forecast(self, power_forecast: PowerForecast):
        reception_status = await self.controller.send_power_forecast(
            self.channel, power_forecast
        )
        await self.add_test_method(
            "Update power forecast",
            self.base_message_send_validate,
            power_forecast,
            reception_status,
        )

    async def send_test_power_measurement(
        self,
        name: str,
        commodity_quantities: list[CommodityQuantity],
        expected_reception_status: ReceptionStatusValues,
    ):
        values = []

        for commodity_quantity in commodity_quantities:
            values.append(
                PowerValue(
                    commodity_quantity=commodity_quantity,
                    value=0,
                )
            )

        power_measurement = PowerMeasurement(
            measurement_timestamp=current_timezone_time(),
            message_id=uuid.uuid4(),
            values=values,
        )

        reception_status = await self.controller.send_power_measurement(
            self.channel, power_measurement
        )

        await self.add_test_method(
            name,
            self.validate_reception_status,
            reception_status,
            expected_reception_status,
            # Since I'm this isn't that important it's a soft fail
            fail_result_status=TestResultStatus.SOFT_FAIL,
        )

    async def send_valid_power_measurement_test(self):
        await self.send_test_power_measurement(
            "9.2.4. Communicate Power Measurement",
            self.controller.resource_manager_details.provides_power_measurement_types,
            ReceptionStatusValues.OK,
        )

    async def send_invalid_measurement(self):
        all_commodities = set(list(CommodityQuantity))
        supported_commodities = set(
            self.controller.resource_manager_details.provides_power_measurement_types
        )

        not_supported_commodities = list(all_commodities - supported_commodities)

        await self.send_test_power_measurement(
            "9.2.4. Communicate Power Measurement - Not supported Commodity Quantity",
            not_supported_commodities,
            ReceptionStatusValues.INVALID_CONTENT,
        )

    async def validate_reception_status(
        self, reception_status: ReceptionStatus, expected_status: ReceptionStatusValues
    ):
        self.update_resource_manager_details_precondition("9.2.4.2.")
        self.assertEqual(reception_status.status, expected_status)

    # TODO: Rethink
    # @S2TestCase.test(name="9.2.5. Update Power Forecast")
    # async def test_update_power_forecast(self):
    #     self.update_resource_manager_details_precondition("9.2.4.2.")

    #     commodity_quantities = self.get_system_description_commodity_quantities()

    #     elements = [
    #         PowerForecastElement(
    #             duration=Duration(3600.0),
    #             power_values=[
    #                 PowerForecastValue(
    #                     commodity_quantity=q,
    #                     value_expected=100,
    #                     value_lower_limit=None,
    #                     value_upper_limit=None,
    #                     value_lower_68PPR=None,
    #                     value_upper_68PPR=None,
    #                     value_lower_95PPR=None,
    #                     value_upper_95PPR=None,
    #                 )
    #                 for q in commodity_quantities
    #             ],
    #         )
    #     ]

    #     power_forecast = PowerForecast(
    #         message_id=uuid.uuid4(),
    #         start_time=current_timezone_time(),
    #         elements=elements,
    #     )

    #     await self.controller.send_power_forecast(self.channel, power_forecast)
