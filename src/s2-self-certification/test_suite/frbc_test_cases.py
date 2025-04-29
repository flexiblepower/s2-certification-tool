import datetime
import json
import logging
import uuid

from certificate.certificate import (
    ComplianceFinding,
    ComplianceParameter,
    ComplianceReport,
    ComplianceStatus,
)
from config import FRBCTestConfig, PEBCTestConfig
from connection import Connection
from controllers.frbc_controller import FRBCController
from s2python.common import PowerMeasurement, ControlType as ProtocolControlType
from s2python.frbc import (
    FRBCActuatorStatus,
    FRBCStorageDescription,
    FRBCStorageStatus,
    FRBCSystemDescription,
    FRBCUsageForecast,
)
from test_suite.base_test_case import NoSelectionTestCase
from test_suite.test_suite import S2TestCase

logger = logging.getLogger(__name__)


class FRBCTestCase(NoSelectionTestCase):
    control_type = ProtocolControlType.FILL_RATE_BASED_CONTROL

    TIMEOUT = 5

    controller: FRBCController
    config: FRBCTestConfig

    def __init__(
        self,
        config: FRBCTestConfig,
        connection: Connection,
        controller: FRBCController,
        report: ComplianceReport,
    ):
        super().__init__(config, connection, controller, report)

    async def setup(self):
        await self.controller._system_description_received.wait()

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

    @S2TestCase.test
    async def test_receive_frbc_system_description(self):
        await self.wait_for_system_description()

        finding = ComplianceFinding(message_type=FRBCSystemDescription)

        message = await self.check_receive_message_type(FRBCSystemDescription, finding)

        self.report.add_finding(finding)

    @S2TestCase.test
    async def test_receive_actuator_status(self):

        finding = ComplianceFinding(message_type=FRBCActuatorStatus)

        message = await self.check_receive_message_type(FRBCActuatorStatus, finding)

        self.report.add_finding(finding)

    @S2TestCase.test
    async def test_receive_storage_status(self):

        finding = ComplianceFinding(message_type=FRBCStorageStatus)

        message = await self.check_receive_message_type(FRBCStorageStatus, finding)

        self.report.add_finding(finding)

    @S2TestCase.test
    async def test_receive_usage_forecast(self):

        finding = ComplianceFinding(message_type=FRBCUsageForecast)

        message = await self.check_receive_message_type(FRBCUsageForecast, finding)

        self.report.add_finding(finding)
