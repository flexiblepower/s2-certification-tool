import logging

from testsuites.certificate.certificate import (
    ComplianceFinding,
    ComplianceStatus,
)
from testsuites.test_suite.test_suite import S2TestCase
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
