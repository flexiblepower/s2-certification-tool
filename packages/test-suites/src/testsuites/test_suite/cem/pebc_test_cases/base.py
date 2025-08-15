import abc
import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Awaitable
import uuid
from connectivity.s2_channel import S2Channel

from connectivity.config import PEBCCEMTestConfig
from testsuites.certificate.certificate import ComplianceReport
from testsuites.controllers.cem.pebc_controller import PEBCCEMController
from testsuites.test_logger import TestLogger
from testsuites.test_suite.cem.not_controllable import NotControllableCEMTestCase
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
    ReceptionStatusValues,
    ReceptionStatus,
    RevokableObjects,
)
from s2python.message import S2Message
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


class PEBCBaseScenarioTestCase(NotControllableCEMTestCase):
    control_type = ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL

    TIMEOUT = 5

    controller: PEBCCEMController
    config: PEBCCEMTestConfig

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

        self._pebc_power_constraints_sent_event = asyncio.Event()
        self._pebc_energy_constraints_sent_event = asyncio.Event()
        self._received_instruction_event = asyncio.Event()

        self.message_handlers[RevokeObject] = self.handle_revoke
        self.message_handlers[PEBCInstruction] = self.handle_instruction

    async def setup(self):
        await super().setup()

        self.assertEqual(
            self.controller.control_type,
            ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL,
            "Precondition Activate Control Type not met",
        )
        self.test_logger.success("Precondition Activate Control Type Met")

    def create_energy_constraint(
        self,
        upper_average_power,
        lower_average_power,
        commodity_quantity=CommodityQuantity.ELECTRIC_POWER_L1,
    ):
        return PEBCEnergyConstraint(
            id=uuid.uuid4(),
            message_id=uuid.uuid4(),
            commodity_quantity=commodity_quantity,
            upper_average_power=upper_average_power,
            lower_average_power=lower_average_power,
            valid_from=current_timezone_time(),
            valid_until=current_timezone_time() + timedelta(hours=1),
        )

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

    async def send_power_constraint(self, power_constraints: PEBCPowerConstraints):
        reception_status = await self.controller.send_pebc_power_constraint(
            self.channel, power_constraints
        )

        test_name = "9.3.1. Update Power Constraints"
        if not self._pebc_power_constraints_sent_event.is_set():
            test_name += " (Initial)"
        self._pebc_power_constraints_sent_event.set()

        await self.add_test_method(
            test_name,
            self.base_message_send_validate,
            power_constraints,
            reception_status,
        )

    async def revoke_power_constraint(self):
        await self.controller.revoke_pebc_power_constraint(self.channel)
        self._pebc_power_constraints_sent_event.clear()

    async def send_energy_constraint(self, energy_constraint: PEBCEnergyConstraint):
        reception_status = await self.controller.send_pebc_energy_constraint(
            self.channel, energy_constraint
        )

        test_name = "Update Energy Constraints"
        if not self._pebc_energy_constraints_sent_event.is_set():
            test_name += " (Initial)"

        self._pebc_energy_constraints_sent_event.set()

        await self.add_test_method(
            test_name,
            self.base_message_send_validate,
            energy_constraint,
            reception_status,
        )

    async def revoke_energy_constraint(self):
        await self.controller.revoke_pebc_energy_constraint(self.channel)
        self._pebc_energy_constraints_sent_event.clear()

    async def send_power_measurement(self, power_measurement: PowerMeasurement):
        reception_status = await self.controller.send_power_measurement(
            self.channel, power_measurement
        )

        await self.add_test_method(
            "9.2.4. Communicate Power Measurement",
            self.base_message_send_validate,
            power_measurement,
            reception_status,
        )

    async def send_power_forecast(self, power_forecast: PowerForecast):
        reception_status = await self.controller.send_power_forecast(
            self.channel, power_forecast
        )

        await self.add_test_method(
            "9.2.5. Update Power Forecast",
            self.base_message_send_validate,
            power_forecast,
            reception_status,
        )

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

    @abc.abstractmethod
    async def validate_instruction(self, instruction: PEBCInstruction):
        pass

    async def handle_instruction(
        self, instruction: PEBCInstruction, channel: S2Channel, send_okay: Awaitable
    ):

        self.test_logger.info(instruction)

        await self.add_test_method(
            "Receive Instruction", self.validate_instruction, instruction
        )

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
        self.assertIn(
            revoke_message,
            [RevokableObjects.PEBC_Instruction],
            "Invalid revoke message received.",
        )
