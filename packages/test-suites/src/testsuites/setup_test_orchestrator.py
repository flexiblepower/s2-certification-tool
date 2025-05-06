from datetime import datetime
from typing import Dict

from s2python.common import ControlType as ProtocolControlType
from testsuites.certificate.certificate import ComplianceReport
from testsuites.controllers import (
    Controller,
    BaseController,
    PEBCController,
    FRBCController,
)
from testsuites.orchestrator import IntegrationTestOrchestrator, Orchestrator
from testsuites.test_suite import PEBCTestCase, TestSuiteBuilder
from testsuites.test_suite.frbc_test_cases import FRBCTestCase
from connectivity.config import Config


def create_controllers_dict_with_config(
    config: Config, report: ComplianceReport
) -> Dict[ProtocolControlType, Controller]:
    controllers: Dict[ProtocolControlType, Controller] = {}

    controllers[ProtocolControlType.NO_SELECTION] = BaseController()

    if config.control_types.frbc and config.control_types.frbc.enabled:
        controllers[ProtocolControlType.FILL_RATE_BASED_CONTROL] = FRBCController()

    if config.control_types.pebc and config.control_types.pebc.enabled:
        controllers[ProtocolControlType.POWER_ENVELOPE_BASED_CONTROL] = PEBCController()

    return controllers


def create_test_orchestrator(config: Config) -> Orchestrator:
    report = ComplianceReport(timestamp=datetime.now())

    controllers = create_controllers_dict_with_config(config, report)

    test_suite = (
        TestSuiteBuilder(config.control_types, report)
        .with_test_case(PEBCTestCase)
        .with_test_case(FRBCTestCase)
        .build()
    )

    orchestrator = IntegrationTestOrchestrator(
        available_control_types=controllers, test_suite=test_suite, report=report
    )

    return orchestrator
