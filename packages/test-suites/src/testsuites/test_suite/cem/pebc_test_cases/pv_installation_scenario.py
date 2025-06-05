import asyncio
from typing import Awaitable
import uuid
from datetime import timedelta
from connectivity.config import PEBCCEMTestConfig
from connectivity.s2_channel import S2Channel
from testsuites.certificate.certificate import ComplianceReport
from testsuites.controllers.cem.pebc_controller import PEBCCEMController
from testsuites.test_logger import TestLogger
from .base import PEBCBaseScenarioTestCase, PowerForecastData

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
    RevokableObjects,
)
from s2python.pebc import (
    PEBCPowerConstraints,
    PEBCEnergyConstraint,
    PEBCAllowedLimitRange,
    PEBCPowerEnvelopeConsequenceType,
    PEBCPowerEnvelopeElement,
    PEBCPowerEnvelopeLimitType,
    PEBCInstruction,
)
from testsuites.util import current_timezone_time


class PEBCPVPanelScenarioTestCase(PEBCBaseScenarioTestCase):
    name = "Photovoltaic Panel Scenario Test Case"

    _received_instruction_event: asyncio.Event

    def __init__(
        self,
        config: PEBCCEMTestConfig,
        channel: S2Channel,
        controller: PEBCCEMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

        self.create_power_constraint()
        self.create_energy_constraint()

        self._received_instruction_event = asyncio.Event()

        self.message_handlers[PEBCInstruction] = self.handle_instruction

    def create_power_constraint(self):

        self.upper_limit = PEBCAllowedLimitRange(
            abnormal_condition_only=False,
            commodity_quantity=CommodityQuantity.ELECTRIC_POWER_L1,
            limit_type=PEBCPowerEnvelopeLimitType.UPPER_LIMIT,
            range_boundary=NumberRange(start_of_range=0, end_of_range=0),
        )
        self.lower_limit = PEBCAllowedLimitRange(
            abnormal_condition_only=False,
            commodity_quantity=CommodityQuantity.ELECTRIC_POWER_L1,
            limit_type=PEBCPowerEnvelopeLimitType.LOWER_LIMIT,
            range_boundary=NumberRange(start_of_range=0, end_of_range=-2000),
        )

        self.power_constraint = PEBCPowerConstraints(
            message_id=uuid.uuid4(),
            id=uuid.uuid4(),
            allowed_limit_ranges=[self.lower_limit, self.upper_limit],
            consequence_type=PEBCPowerEnvelopeConsequenceType.VANISH,
            valid_from=current_timezone_time(),
            valid_until=current_timezone_time() + timedelta(hours=1),
        )

    def create_energy_constraint(self):
        # PV doesn't have energy constraint
        pass

    def create_power_measurement(
        self, power_values: list[tuple[CommodityQuantity, float]]
    ) -> PowerMeasurement:
        measurements = []
        for commodity_quantity, value in power_values:
            measurements.append(
                PowerValue(
                    commodity_quantity=commodity_quantity,
                    value=value,
                )
            )

        return PowerMeasurement(
            message_id=uuid.uuid4(),
            measurement_timestamp=current_timezone_time(),
            values=measurements,
        )

    async def generate_tests(self):
        await super().generate_tests()

        await self.add_trigger_method(
            self.send_power_constraint, self.power_constraint, wait_time=0
        )

        await self.add_trigger_method(
            self.update_power_forecast,
            self.create_power_forecast(
                [
                    [PowerForecastData(CommodityQuantity.ELECTRIC_POWER_L1, 0)],
                ]
            ),
            wait_time=0,
        )
        await self.add_trigger_method(
            self.update_power_measurement,
            self.create_power_measurement(
                [(CommodityQuantity.ELECTRIC_POWER_L1, -2000)]
            ),
            wait_time=0,
        )

        await self.add_trigger_method(
            None,
            event=self._received_instruction_event,
            wait_time=self.config.instruction_wait_timeout,
        )

    async def handle_instruction(
        self, instruction: PEBCInstruction, channel: S2Channel, send_okay: Awaitable
    ):

        self.test_logger.info(instruction)

        await send_okay
        self._received_instruction_event.set()

    async def handle_revoke(
        self, revoke_message: RevokeObject, channel: S2Channel, send_okay: Awaitable
    ):
        await self.handle_with_original_handler(revoke_message, channel, send_okay)

        await self.add_test_method(
            "Revoke PEBC Instruction.", self.validate_receive_revoke_message
        )

    async def validate_receive_revoke_message(self, revoke_message):
        # The only thing that the CEM can revoke in an instruction.
        self.assertIn(revoke_message, [RevokableObjects.PEBC_Instruction])

    # async def generate_tests(self):
    #     await super().generate_tests()

    #     dupe_power_constraint = self.power_constraint.model_copy()
    #     dupe_power_constraint.message_id = uuid.uuid4()
    #     await self.add_test_method(
    #         "9.3.1. Update Power Constraints (Initial)",
    #         self.send_power_constraint,
    #         dupe_power_constraint,
    #     )

    #     await self.add_test_method(
    #         "9.3.1. Update Power Constraints",
    #         self.send_power_constraint,
    #         self.power_constraint,
    #     )

    #     # ! No energy constraints since PV doesn't have them.

    #     await self.add_test_method(
    #         "9.2.5. Update Power Forecast",
    #         self.update_power_forecast,
    #         self.create_power_forecast(
    #             [
    #                 [PowerForecastData(CommodityQuantity.ELECTRIC_POWER_L1, 0)],
    #             ]
    #         ),
    #     )
    #     await self.add_test_method(
    #         "9.2.4. Communicate Power Measurement",
    #         self.update_power_measurement,
    #         self.create_power_measurement(
    #             [(CommodityQuantity.ELECTRIC_POWER_L1, -2000)]
    #         ),
    #         10,
    #     )

    #     await self.add_test_method(
    #         "9.2.4. Communicate Power Measurement",
    #         self.update_power_measurement,
    #         self.create_power_measurement(
    #             [(CommodityQuantity.ELECTRIC_POWER_L1, -1800)]
    #         ),
    #         60,
    #     )

    #     await self.add_test_method(
    #         "Wait for instruction",
    #         self.wait_for_instruction,
    #         self.config.instruction_wait_timeout,
    #     )

    #     await self.add_test_method(
    #         "9.3.2. Revoke Power Constraints",
    #         self.revoke_power_constraint,
    #     )
