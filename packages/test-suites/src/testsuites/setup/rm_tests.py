from connectivity.config import (
    Config,
)

from testsuites.test_suite.rm.base_test_case import NotControllableRMTestCase
from testsuites.test_suite.rm.frbc_test_cases import FRBCTestCase
from testsuites.test_suite.rm.pebc_test_cases import PEBCTestCase
from testsuites.test_suite.test_suite import TestSuite, TestSuiteBuilder
from testsuites.test_logger import AbstractTestLogger, TestLogger
from testsuites.certificate.certificate import ComplianceReport


def build_rm_test_suite(
    config: Config, report: ComplianceReport, test_logger: AbstractTestLogger
) -> TestSuiteBuilder:
    # Returns a builder so that it can be extended if needed elsewhere.
    return (
        TestSuiteBuilder(config.roles, report, test_logger)
        # RM Not Controllable Test Cases
        .with_test_case(NotControllableRMTestCase)
        # RM PEBC Test Cases
        .with_test_case(PEBCTestCase)
        # RM FRBC Test Cases
        .with_test_case(FRBCTestCase)
    )
