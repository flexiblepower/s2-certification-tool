from connectivity.config import Config
from testsuites.test_logger import AbstractTestLogger
from testsuites.certificate.certificate import ComplianceReport
from testsuites.test_suite.test_suite import TestSuiteBuilder

from .frbc_test_cases import (
    FRBCElectricVehicleScenarioTestCase,
    FRBCBatteryScenarioTestCase,
)
from .pebc_test_cases import (
    PEBCPVPanelScenarioTestCase,
    PEBCElectricVehicleCurtailScenarioTestCase,
)
from .not_controllable import NotControllableCEMTestCase


def build_cem_test_suite(
    config: Config, report: ComplianceReport, test_logger: AbstractTestLogger
) -> TestSuiteBuilder:
    # Returns a builder so that it can be extended if needed elsewhere.
    return (
        TestSuiteBuilder(config.roles, report, test_logger)
        # ! Not Controllable Test Cases
        .with_test_case(NotControllableCEMTestCase)
        # ! FRBC Test Cases
        # .with_test_case(FRBCElectricVehicleScenarioTestCase)
        # .with_test_case(FRBCBatteryScenarioTestCase)
        # ! PEBC Test Case
        # .with_test_case(PEBCPVPanelScenarioTestCase).with_test_case(
        #     PEBCElectricVehicleCurtailScenarioTestCase
        # )
    )
