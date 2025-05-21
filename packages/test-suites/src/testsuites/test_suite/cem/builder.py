from testsuites.test_logger import AbstractTestLogger, TestLogger
from testsuites.certificate.certificate import ComplianceReport
from testsuites.test_suite.test_suite import TestSuite, TestSuiteBuilder
from connectivity.config import Config


def build_cem_test_suite(
    config: Config, report: ComplianceReport, test_logger: AbstractTestLogger
) -> TestSuiteBuilder:
    # Returns a builder so that it can be extended if needed elsewhere.
    return TestSuiteBuilder(config.roles, report, test_logger)
