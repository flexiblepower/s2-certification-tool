from testsuites.test_logger import AbstractTestLogger, TestLogger
from testsuites.certificate.certificate import ComplianceReport
from testsuites.test_suite.test_suite import TestSuite, TestSuiteBuilder
from connectivity.config import Config

from .pebc_test_cases import (
    PEBCTestCase,
)
from .base_test_case import NotControllableRMTestCase
from .frbc_test_cases import (
    FRBCActuatorStatusTestCase,
    FRBCStorageStatusTestCase,
    FRBCSystemDescriptionTestCase,
    FRBCUsageForecastTestCase,
)


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
        .with_test_case(FRBCUsageForecastTestCase)
        .with_test_case(FRBCActuatorStatusTestCase)
        .with_test_case(FRBCSystemDescriptionTestCase)
        .with_test_case(FRBCStorageStatusTestCase)
    )
