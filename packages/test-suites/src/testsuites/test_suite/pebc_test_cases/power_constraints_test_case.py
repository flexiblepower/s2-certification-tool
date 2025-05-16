import logging

from testsuites.certificate.certificate import (
    TestSuiteResults,
    TestResultStatus,
)
from testsuites.test_suite.test_suite import S2TestCase
from .base import PEBCTestCase

logger = logging.getLogger(__name__)


class PEBCPowerConstraintsTestCase(PEBCTestCase):
    name = "Test receive PEBCPowerConstraints"

    @S2TestCase.test("Receive PEBC Power Constraints")
    async def validate_power_constraints_set(self):
        await self.wait_until_power_constraints_set()

        self.test_logger.success("Test Receive PEBC Power Constraints")
