import datetime
import logging
from typing import Dict, List
import uuid

from testsuites.certificate.certificate import (
    ComplianceFinding,
    ComplianceParameter,
    ComplianceReport,
    ComplianceStatus,
)
from connectivity.config import BaseTestConfig, PEBCTestConfig
from testsuites.controllers.controller import Controller
from testsuites.controllers.pebc_controller import PEBCController
from s2python.common import (
    ControlType as ProtocolControlType,
    PowerMeasurement,
    InstructionStatusUpdate,
    CommodityQuantity,
)
from s2python.pebc import (
    PEBCAllowedLimitRange,
    PEBCInstruction,
    PEBCPowerConstraints,
    PEBCPowerEnvelope,
    PEBCPowerEnvelopeElement,
)
from testsuites.test_suite.base_test_case import NoSelectionTestCase
from testsuites.test_suite.test_suite import S2TestCase
from connectivity.s2_channel import S2Channel
from .base import PEBCTestCase

logger = logging.getLogger(__name__)


class PEBCPowerConstraintsTestCase(PEBCTestCase):
    finding = ComplianceFinding(test="Test receive PEBCPowerConstraints")

    @S2TestCase.test
    async def validate_power_constraints_set(self):
        await self.wait_until_power_constraints_set()

        self.add_finding_param(
            name="PEBCPowerConstraints Received.", status=ComplianceStatus.PASS
        )
