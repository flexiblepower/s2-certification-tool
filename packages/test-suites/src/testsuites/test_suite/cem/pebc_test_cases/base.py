import asyncio
from dataclasses import dataclass
import logging
import uuid
from connectivity.s2_channel import S2Channel

from connectivity.config import PEBCCEMTestConfig
from testsuites.certificate.certificate import ComplianceReport
from testsuites.controllers.cem.pebc_controller import PEBCCEMController
from testsuites.test_logger import TestLogger
from testsuites.test_suite.test_suite import NotApplicableTestException, S2TestCase
from testsuites.util import current_timezone_time

logger = logging.getLogger(__name__)

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


@dataclass
class PowerForecastData:
    commodity_quantity: CommodityQuantity
    value: int
    duration: int = 3600
    variance: float = 0.5


class PEBCBaseScenarioTestCase(S2TestCase):
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL

    TIMEOUT = 5

    controller: PEBCCEMController
    config: PEBCCEMTestConfig

    def __init__(
        self,
        config: PEBCCEMTestConfig,
        channel: S2Channel,
        controller: PEBCCEMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

        self._pebc_power_constraints_sent_event = asyncio.Event()
        self._pebc_energy_constraints_sent_event = asyncio.Event()

    async def setup(self):
        await super().setup()

        self.assertEqual(
            self.controller.control_type,
            ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL,
            "Precondition Activate Control Type not met",
        )
        self.test_logger.success("Precondition Activate Control Type Met")

    def update_power_constraints_precondition(self, precondition_id: str | None = None):
        """Tests the power constraints have been set as precondition.

        Args:
            precondition_id (string): The ID from the S2 Specification
        """
        # try:
        self.assertTrue(
            self._pebc_power_constraints_sent_event.is_set(),
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update Power Constraint' not complete.",
        )
        self.test_logger.success(
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update Power Constraint' is complete."
        )

    def update_energy_constraints_precondition(
        self, precondition_id: str | None = None
    ):
        """Tests the energy constraints have been set as precondition.

        Args:
            precondition_id (string): The ID from the S2 Specification
        """
        # try:
        self.assertTrue(
            self._pebc_energy_constraints_sent_event.is_set(),
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update Energy Constraint' not complete.",
        )
        self.test_logger.success(
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update Energy Constraint' is complete."
        )

    async def test_send_pebc_power_constraint(
        self, power_constraints: PEBCPowerConstraints
    ):
        await self.controller.send_pebc_power_constraint(
            self.channel, power_constraints
        )
        self._pebc_power_constraints_sent_event.set()

    async def test_revoke_power_constraint(self):
        await self.controller.revoke_pebc_power_constraint(self.channel)
        self._pebc_power_constraints_sent_event.clear()

    async def test_send_energy_constraint(
        self, energy_constraint: PEBCEnergyConstraint
    ):
        await self.controller.send_pebc_energy_constraint(
            self.channel, energy_constraint
        )
        self._pebc_energy_constraints_sent_event.set()

    async def test_revoke_energy_constraint(self):
        await self.controller.revoke_pebc_energy_constraint(self.channel)
        self._pebc_energy_constraints_sent_event.clear()

    async def test_update_power_measurement(
        self, power_measurement: PowerMeasurement, wait_time=0
    ):
        await self.controller.send_power_measurement(self.channel, power_measurement)

        await asyncio.sleep(wait_time)

    async def test_update_power_forecast(
        self, power_forecast: PowerForecast, wait_time=0
    ):
        await self.controller.send_power_forecast(self.channel, power_forecast)

        await asyncio.sleep(wait_time)

    async def wait_for_instruction(self, wait_time=10):
        try:
            self.test_logger.info(f"Waiting {wait_time} seconds for an instruction...")
            instruction = await self.controller.message_awaiter.wait_for_message(
                PEBCInstruction, timeout=wait_time
            )
            self.test_logger.info(instruction)
        except TimeoutError as e:
            raise NotApplicableTestException("No instruction received.")

    def create_power_forecast(
        self, values: list[list[PowerForecastData]]
    ) -> PowerForecast:
        elements = []
        for period_value in values:
            for period_data in period_value:
                elements.append(
                    PowerForecastElement(
                        duration=Duration(period_data.duration),
                        power_values=[
                            PowerForecastValue(
                                commodity_quantity=period_data.commodity_quantity,
                                value_expected=period_data.value,
                                value_lower_limit=period_data.value
                                - period_data.variance * period_data.value,
                                value_upper_limit=period_data.value
                                + period_data.variance * period_data.value,
                                value_lower_68PPR=None,
                                value_upper_68PPR=None,
                                value_lower_95PPR=None,
                                value_upper_95PPR=None,
                            )
                        ],
                    )
                )

        return PowerForecast(
            message_id=uuid.uuid4(),
            elements=elements,
            start_time=current_timezone_time(),
        )
