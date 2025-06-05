import abc
import asyncio
import logging
from typing import Awaitable, Optional
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
    RevokableObjects,
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
from testsuites.test_suite.test_suite import (
    NotApplicableTestException,
    S2TestCase,
    TestLogger,
)
from connectivity.s2_channel import S2Channel

logger = logging.getLogger(__name__)


class FRBCCEMTestCase(NotControllableCEMTestCase):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL

    TIMEOUT = 5

    controller: FRBCCEMController
    config: FRBCCEMTestConfig

    _received_instruction_event: asyncio.Event

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
        self._received_instruction_event = asyncio.Event()

        self.message_handlers[RevokeObject] = self.handle_revoke
        self.message_handlers[FRBCInstruction] = self.handle_instruction

    async def setup(self):
        await super().setup()

        self.assertEqual(
            self.controller.control_type,
            ProtocolControlType.FILL_RATE_BASED_CONTROL,
            "Precondition Activate Control Type not met",
        )
        self.test_logger.success("Precondition Activate Control Type Met")

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

    async def send_frbc_system_description(
        self, system_description: FRBCSystemDescription
    ):
        # Only send the FRBC System Description once.
        reception_status = await self.controller.send_frbc_system_description(
            self.channel, system_description
        )
        test_name = "9.6.1 Update System Description"
        if not self._frbc_system_description_sent_event.is_set():
            test_name += " (initial)"
        self._frbc_system_description_sent_event.set()

        await self.add_test_method(
            test_name,
            self.base_message_send_validate,
            system_description,
            reception_status,
        )

    async def send_revoke_system_description(self):
        self.update_system_description_precondition("9.6.2.2.")

        reception_status = await self.controller.revoke_frbc_system_description(
            self.channel
        )

        # Reset event since it's been revoked.
        self._frbc_system_description_sent_event.clear()

        # await self.add_test_method(
        #     "9.6.2. Revoke System Description",
        #     self.base_message_send_validate,

        #     reception_status,
        # )

    async def send_leakage_behaviour(self, leakage_behaviour: FRBCLeakageBehaviour):
        self.update_system_description_precondition("9.6.3.2.")

        reception_status = await self.controller.send_frbc_leakage_behavior(
            self.channel, leakage_behaviour
        )
        test_name = "9.6.3. Update Leakage Behaviour"
        if not self._frbc_leakage_behavior_sent_event.is_set():
            test_name += " (initial)"
        self._frbc_leakage_behavior_sent_event.set()

        await self.add_test_method(
            test_name,
            self.base_message_send_validate,
            leakage_behaviour,
            reception_status,
        )

    async def send_revoke_leakage_behaviour(self):
        self.assertTrue(
            self._frbc_system_description_sent_event.is_set(),
            "9.6.4.2. Task Precondition 'Update Leakage Behaviour' not complete.",
        )
        self.test_logger.success(
            "9.6.4.2. Task Precondition 'Update Leakage Behaviour' is complete.",
        )

        reception_status = await self.controller.revoke_leakage_behaviour(self.channel)

        self._frbc_leakage_behavior_sent_event.clear()

    async def send_usage_forecast(self, forecast: FRBCUsageForecast):
        self.update_system_description_precondition("9.6.5.2.")

        reception_status = await self.controller.send_frbc_usage_forecast(
            self.channel, forecast
        )
        await self.add_test_method(
            "Update usage forecast",
            self.base_message_send_validate,
            forecast,
            reception_status,
        )

    async def send_actuator_status(self, actuator_status: FRBCActuatorStatus):
        self.update_system_description_precondition()

        reception_status = await self.controller.send_actuator_status(
            self.channel, actuator_status
        )
        await self.add_test_method(
            "Update actuator forecast",
            self.base_message_send_validate,
            actuator_status,
            reception_status,
        )

    async def send_storage_status(self, storage_status: FRBCStorageStatus):
        self.update_system_description_precondition()

        reception_status = await self.controller.send_storage_status(
            self.channel, storage_status
        )

        await self.add_test_method(
            "Update actuator forecast",
            self.base_message_send_validate,
            storage_status,
            reception_status,
        )

    async def send_power_measurement(self, power_measurement: PowerMeasurement):
        self.update_system_description_precondition()
        return await super().send_power_measurement(power_measurement)

    async def wait_for_instruction(self, wait_time=10):
        try:
            instruction = await self.controller.message_awaiter.wait_for_message(
                FRBCInstruction, timeout=wait_time
            )
            self.test_logger.info(instruction)
        except TimeoutError as e:
            raise NotApplicableTestException("No instruction received.")

    @abc.abstractmethod
    async def validate_instruction(self, instruction: FRBCInstruction):
        pass

    async def handle_instruction(
        self, instruction: FRBCInstruction, channel: S2Channel, send_okay: Awaitable
    ):
        await self.handle_with_original_handler(instruction, channel, send_okay)

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
            [RevokableObjects.FRBC_Instruction],
            "Invalid revoke message received.",
        )
