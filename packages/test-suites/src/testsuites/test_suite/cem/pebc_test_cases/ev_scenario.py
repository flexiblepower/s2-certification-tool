import asyncio
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
)
from s2python.pebc import (
    PEBCPowerConstraints,
    PEBCEnergyConstraint,
    PEBCAllowedLimitRange,
    PEBCInstruction,
    PEBCPowerEnvelope,
    PEBCPowerEnvelopeConsequenceType,
    PEBCPowerEnvelopeElement,
    PEBCPowerEnvelopeLimitType,
)
from testsuites.util import current_timezone_time


class PEBCElectricVehicleCurtailScenarioTestCase(PEBCBaseScenarioTestCase):
    name = "Electric Vehicle Curtail Charging Scenario Test Case"

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

        self._received_instruction_event = asyncio.Event()

    def create_power_constraint(self):

        self.upper_limit = PEBCAllowedLimitRange(
            abnormal_condition_only=False,
            commodity_quantity=CommodityQuantity.ELECTRIC_POWER_L1,
            limit_type=PEBCPowerEnvelopeLimitType.UPPER_LIMIT,
            range_boundary=NumberRange(start_of_range=0, end_of_range=2000),
        )
        self.lower_limit = PEBCAllowedLimitRange(
            abnormal_condition_only=False,
            commodity_quantity=CommodityQuantity.ELECTRIC_POWER_L1,
            limit_type=PEBCPowerEnvelopeLimitType.LOWER_LIMIT,
            range_boundary=NumberRange(start_of_range=0, end_of_range=0),
        )

        self.power_constraint = PEBCPowerConstraints(
            message_id=uuid.uuid4(),
            id=uuid.uuid4(),
            allowed_limit_ranges=[self.lower_limit, self.upper_limit],
            consequence_type=PEBCPowerEnvelopeConsequenceType.DEFER,
            valid_from=current_timezone_time(),
            valid_until=current_timezone_time() + timedelta(hours=1),
        )

    async def generate_tests(self):
        await super().generate_tests()

        await self.add_trigger_method(self.send_power_constraint, self.power_constraint)

        off_energy_constraint = self.create_energy_constraint(0, 0)
        await self.add_trigger_method(
            self.send_energy_constraint, off_energy_constraint
        )

        await self.add_trigger_method(
            self.send_power_forecast,
            self.create_power_forecast(
                [
                    [
                        PowerForecastData(
                            CommodityQuantity.ELECTRIC_POWER_L1, 0, variance=0
                        )
                    ],
                    [
                        PowerForecastData(
                            CommodityQuantity.ELECTRIC_POWER_L1, 0, variance=0
                        )
                    ],
                ]
            ),
        )

        await self.add_trigger_method(
            self.send_power_measurement,
            self.create_power_measurement([(CommodityQuantity.ELECTRIC_POWER_L1, 0)]),
        )

        await self.add_trigger_method(None, wait_time=10)

        # Car plugged in. Starting to charge.
        charging_energy_constraint = self.create_energy_constraint(2000, 1000)
        await self.add_trigger_method(
            self.send_energy_constraint, charging_energy_constraint
        )

        await self.add_trigger_method(
            self.send_power_forecast,
            self.create_power_forecast(
                [
                    [
                        PowerForecastData(
                            CommodityQuantity.ELECTRIC_POWER_L1, 2000, variance=0
                        )
                    ],
                    [
                        PowerForecastData(
                            CommodityQuantity.ELECTRIC_POWER_L1, 2000, variance=0
                        )
                    ],
                ]
            ),
        )

        await self.add_trigger_method(
            self.send_power_measurement,
            self.create_power_measurement(
                [(CommodityQuantity.ELECTRIC_POWER_L1, 2000)]
            ),
        )

        await self.add_trigger_method(
            None,
            event=self._received_instruction_event,
            wait_time=self.config.instruction_wait_timeout,
        )

        # Wait 10 seconds after receiving instruction
        await self.add_trigger_method(None, wait_time=10)

        await self.add_trigger_method(self.revoke_power_constraint)
        await self.add_trigger_method(self.revoke_energy_constraint)

    async def fold(self):
        await super().generate_tests()
        self.test_logger.info("Starting in a not charging state.")

        await self.add_test_method(
            "9.3.1. Update Power Constraints",
            self.send_power_constraint,
            self.power_constraint,
        )

        off_energy_constraint = self.create_energy_constraint(0, 0)
        await self.add_test_method(
            "Update Energy Constraint",
            self.send_energy_constraint,
            off_energy_constraint,
        )

        await self.add_test_method(
            "9.2.5. Update Power Forecast",
            self.send_power_forecast,
            self.create_power_forecast(
                [
                    [
                        PowerForecastData(
                            CommodityQuantity.ELECTRIC_POWER_L1, 0, variance=0
                        )
                    ],
                    [
                        PowerForecastData(
                            CommodityQuantity.ELECTRIC_POWER_L1, 0, variance=0
                        )
                    ],
                ]
            ),
        )

        # Send Measurement when not charging
        await self.add_test_method(
            "9.2.4. Communicate Power Measurement",
            self.send_power_measurement,
            self.create_power_measurement([(CommodityQuantity.ELECTRIC_POWER_L1, 0)]),
            10,
        )
        self.test_logger.info("Changing to a charging state.")

        # Car plugged in. Starting to charge.
        charging_energy_constraint = self.create_energy_constraint(2000, 1000)
        await self.add_test_method(
            "Update Energy Constraint",
            self.send_energy_constraint,
            charging_energy_constraint,
        )

        await self.add_test_method(
            "9.2.5. Update Power Forecast",
            self.send_power_forecast,
            self.create_power_forecast(
                [
                    [
                        PowerForecastData(
                            CommodityQuantity.ELECTRIC_POWER_L1, 2000, variance=0
                        )
                    ],
                    [
                        PowerForecastData(
                            CommodityQuantity.ELECTRIC_POWER_L1, 2000, variance=0
                        )
                    ],
                ]
            ),
        )

        await self.add_test_method(
            "9.2.4. Communicate Power Measurement",
            self.send_power_measurement,
            self.create_power_measurement(
                [(CommodityQuantity.ELECTRIC_POWER_L1, 2000)]
            ),
            # 60,
        )

        await self.add_test_method(
            "Wait for instruction",
            self.wait_for_instruction,
            self.config.instruction_wait_timeout,
        )

        await self.add_test_method(
            "9.3.2. Revoke Power Constraints",
            self.revoke_power_constraint,
        )
