import asyncio
import logging
import uuid

from s2python.frbc import (
    FRBCSystemDescription,
    FRBCStorageDescription,
    FRBCActuatorDescription,
    FRBCOperationMode,
    FRBCOperationModeElement,
    FRBCLeakageBehaviour,
    FRBCLeakageBehaviourElement,
    FRBCUsageForecast,
    FRBCUsageForecastElement,
    FRBCActuatorStatus,
    FRBCStorageStatus,
    FRBCInstruction,
)
from s2python.common import (
    ControlType as ProtocolControlType,
    EnergyManagementRole,
    PowerForecast,
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

from testsuites.controllers.cem.not_controllable_controller import (
    NotControllableCEMController,
)
from testsuites.test_suite.cem.not_controllable import NotControllableCEMTestCase
from testsuites.util import current_timezone_time
from testsuites.certificate.certificate import (
    ComplianceReport,
)
from connectivity.config import FRBCCEMTestConfig
from testsuites.controllers import FRBCCEMController
from testsuites.test_suite.rm.base_test_case import NoSelectionTestCase
from testsuites.test_suite.test_suite import (
    NotApplicableTestException,
    S2TestCase,
    TestLogger,
)
from connectivity.s2_channel import S2Channel

logger = logging.getLogger(__name__)


class FRBCTestCase(NotControllableCEMTestCase):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL

    TIMEOUT = 5

    controller: FRBCCEMController
    config: FRBCCEMTestConfig

    def __init__(
        self,
        config: FRBCCEMTestConfig,
        channel: S2Channel,
        controller: FRBCCEMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)


class FRBCBaseScenarioTestCase(FRBCTestCase):

    def __init__(
        self,
        config: FRBCCEMTestConfig,
        channel: S2Channel,
        controller: FRBCCEMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

        self._frbc_system_description_sent_event = asyncio.Event()
        self._frbc_leakage_behavior_sent_event = asyncio.Event()

    async def setup(self):
        await super().setup()

        self.assertEqual(self.controller.control_type, ProtocolControlType.FILL_RATE_BASED_CONTROL, "Precondition Activate Control Type not met")
        self.test_logger.success(
            "Precondition Activate Control Type Met"
        )

    def update_system_description_precondition(
        self, precondition_id: str | None = None
    ):
        """Tests the system description precondition.

        Args:
            precondition_id (string): The ID from the S2 Specification
        """
        # try:
        self.assertTrue(
            self._frbc_system_description_sent_event.is_set(),
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update System Description' not complete.",
        )
        self.test_logger.success(
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update System Description' is complete."
        )

    async def test_send_frbc_system_description(
        self, system_description: FRBCSystemDescription
    ):
        # Only send the FRBC System Description once.
        await self.controller.send_frbc_system_description(
            self.channel, system_description
        )
        self._frbc_system_description_sent_event.set()

    async def test_revoke_system_description(self):
        self.update_system_description_precondition("9.6.2.2.")

        await self.controller.revoke_frbc_system_description(self.channel)

        # Reset event since it's been revoked.
        self._frbc_system_description_sent_event.clear()

    async def test_update_leakage_behaviour(
        self, leakage_behaviour: FRBCLeakageBehaviour
    ):
        self.update_system_description_precondition("9.6.3.2.")

        await self.controller.send_frbc_leakage_behavior(
            self.channel, leakage_behaviour
        )
        self._frbc_leakage_behavior_sent_event.set()

    async def test_revoke_leakage_behaviour(self):
        self.assertTrue(
            self._frbc_system_description_sent_event.is_set(),
            "9.6.4.2. Task Precondition 'Update Leakage Behaviour' not complete.",
        )
        self.test_logger.success(
            "9.6.4.2. Task Precondition 'Update Leakage Behaviour' is complete.",
        )

        await self.controller.revoke_leakage_behaviour(
            self.channel, self.leakage_behaviour
        )

        self._frbc_leakage_behavior_sent_event.clear()

    async def test_update_usage_forecast(self, forecast: FRBCUsageForecast):
        self.update_system_description_precondition("9.6.5.2.")

        await self.controller.send_frbc_usage_forecast(self.channel, forecast)

    async def test_update_actuator_status(self, actuator_status: FRBCActuatorStatus):
        self.update_system_description_precondition()

        await self.controller.send_actuator_status(self.channel, actuator_status)

    async def test_update_storage_status(self, storage_status: FRBCStorageStatus):
        self.update_system_description_precondition()

        await self.controller.send_storage_status(self.channel, storage_status)

    async def test_update_power_measurement(
        self, power_measurement: PowerMeasurement, wait_time=0
    ):
        self.update_system_description_precondition()

        await self.controller.send_power_measurement(self.channel, power_measurement)

        await asyncio.sleep(wait_time)

    async def wait_for_instruction(self, wait_time=10):
        try:
            instruction = await self.controller.message_awaiter.wait_for_message(
                FRBCInstruction, timeout=wait_time
            )
            self.test_logger.info(instruction)
        except TimeoutError as e:
            raise NotApplicableTestException("No instruction received.")
