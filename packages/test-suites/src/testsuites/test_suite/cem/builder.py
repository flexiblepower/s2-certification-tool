from testsuites.test_logger import AbstractTestLogger, TestLogger
from testsuites.certificate.certificate import ComplianceReport
from testsuites.test_suite.test_suite import TestSuite, TestSuiteBuilder
from connectivity.config import Config
from .frbc_test_cases import (
    FRBCElectricVehicleScenarioTestCase,
    FRBCHeatPumpScenarioTestCase,
)
from .not_controllable import NotControllableCEMController, NotControllableCEMTestCase

# from .pebc_test_cases import


def build_cem_test_suite(
    config: Config, report: ComplianceReport, test_logger: AbstractTestLogger
) -> TestSuiteBuilder:
    # Returns a builder so that it can be extended if needed elsewhere.
    return (
        TestSuiteBuilder(config.roles, report, test_logger)
        .with_test_case(NotControllableCEMTestCase)
        # FRBC Test Cases
        .with_test_case(FRBCElectricVehicleScenarioTestCase)
        .with_test_case(FRBCHeatPumpScenarioTestCase)
        # PEBC Test Case
        # .with_test_case()
    )
