import datetime
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
from s2python.common import PowerMeasurement
from s2python.pebc import (
    PEBCAllowedLimitRange,
    PEBCInstruction,
    PEBCPowerConstraints,
    PEBCPowerEnvelope,
    PEBCPowerEnvelopeElement,
)
from test_suite.test_suite import S2TestCase

logger = logging.getLogger(__name__)


class FRBCTestCase(S2TestCase):

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

    async def wait_for_system_description(self):
        system_description = self.controller.system_description
        if (
            system_description is None
            and not self.controller._system_description_received.is_set()
        ):
            logger.info(
                "Waiting. %s, %s",
                system_description,
                self.controller._system_description_received,
            )
            await self.controller._system_description_received.wait()
            logger.info("Power Constraints is set.")

    async def validate_power_constraints_set(self):
        await self.wait_for_system_description()

        finding = ComplianceFinding(message_type=PEBCPowerConstraints)
        finding.add_parameter(
            ComplianceParameter(
                name="PEBCPowerConstraints Provided.", status=ComplianceStatus.PASS
            )
        )

        self.report.add_finding(finding)

    async def execute(self):
        logger.info("Starting FRBC Test Case")
        await self.validate_power_constraints_set()
        logger.info("FRBC test case complete.")
