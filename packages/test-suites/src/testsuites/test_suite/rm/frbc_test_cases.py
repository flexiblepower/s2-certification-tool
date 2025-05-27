import logging

from testsuites.certificate.certificate import (
    ComplianceReport,
)
from connectivity.config import FRBCRMTestConfig
from testsuites.controllers import FRBCRMController
from s2python.common import ControlType as ProtocolControlType
from .base_test_case import NoSelectionTestCase
from testsuites.test_suite.test_suite import S2TestCase, TestLogger
from connectivity.s2_channel import S2Channel
import logging

from s2python.frbc import (
    FRBCActuatorStatus,
    FRBCStorageStatus,
    FRBCSystemDescription,
    FRBCUsageForecast,
    FRBCLeakageBehaviour,
)

logger = logging.getLogger(__name__)


class FRBCTestCase(NoSelectionTestCase):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL

    TIMEOUT = 5

    controller: FRBCRMController
    config: FRBCRMTestConfig

    def __init__(
        self,
        config: FRBCRMTestConfig,
        channel: S2Channel,
        controller: FRBCRMController,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        super().__init__(config, channel, controller, report, logger)

    async def setup(self):
        await self.controller._system_description_received.wait()

    def update_system_description_precondition(
        self, precondition_id: str | None = None
    ):
        """Tests the system description precondition.

        Args:
            precondition_id (string): The ID from the S2 Specification
        """
        # try:
        self.assertTrue(
            self.controller._system_description_received.is_set(),
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update System Description' not complete.",
        )
        self.test_logger.success(
            f"{precondition_id + ' ' if precondition_id is not None else '' }Task Precondition 'Update System Description' is complete."
        )

    async def wait_for_system_description(self):
        system_description = self.controller.system_description
        if (
            system_description is None
            and not self.controller._system_description_received.is_set()
        ):
            logger.debug(
                "Waiting. %s, %s",
                system_description,
                self.controller._system_description_received,
            )
            await self.controller._system_description_received.wait()
        logger.debug("System description is set.")

    @S2TestCase.test("9.6.1 Update System Description")
    async def test_receive_frbc_system_description(self):
        message = await self.check_receive_message_type(FRBCSystemDescription)

        self.assertEqual(type(message), FRBCSystemDescription)

    @S2TestCase.test("9.6.3. Update Leakage Behaviour")
    async def test_receive_frbc_leakage_behaviour(self):
        self.update_system_description_precondition("9.6.3.2")

        message = await self.check_receive_message_type(FRBCLeakageBehaviour)

        self.assertEqual(type(message), FRBCLeakageBehaviour)

    @S2TestCase.test("Update Actuator Status")
    async def test_receive_actuator_status(self):
        self.update_system_description_precondition()

        message = await self.check_receive_message_type(FRBCActuatorStatus)

        self.assertEqual(type(message), FRBCActuatorStatus)

    @S2TestCase.test("Update Storage Status")
    async def test_receive_storage_status(self):
        self.update_system_description_precondition()

        message = await self.check_receive_message_type(FRBCStorageStatus)

        self.assertEqual(type(message), FRBCStorageStatus)

    @S2TestCase.test("9.6.5. Update Usage Forecast")
    async def test_receive_usage_forecast(self):
        self.update_system_description_precondition("9.6.5.2.")

        message = await self.check_receive_message_type(FRBCUsageForecast)

        self.assertEqual(type(message), FRBCUsageForecast)
