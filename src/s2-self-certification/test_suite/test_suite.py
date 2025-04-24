import abc
import logging
from typing import TYPE_CHECKING, Dict, List, Type

from certificate.certificate import ComplianceReport
from config import BaseTestConfig, ControlTypeTestConfig
from connection import Connection
from controllers.controller import Controller
from s2python.common import ControlType as ProtocolControlType

logger = logging.getLogger(__name__)


class S2TestCase(abc.ABC):
    control_type: ProtocolControlType = ProtocolControlType.NO_SELECTION
    config: BaseTestConfig

    def __init__(
        self,
        config: BaseTestConfig,
        connection: Connection,
        controller: Controller,
        report: ComplianceReport,
    ):
        self.connection = connection
        self.controller = controller
        self.config = config
        self.report = report

    @abc.abstractmethod
    async def execute(self):
        pass


class TestSuite:
    config: ControlTypeTestConfig
    test_cases: Dict[ProtocolControlType, List[Type[S2TestCase]]]
    report: ComplianceReport

    def __init__(self, config: ControlTypeTestConfig, report: ComplianceReport):
        self.test_cases = {}
        self.config = config
        self.report = report

    def add_test_case(self, test_case: Type[S2TestCase]):
        if test_case.control_type in self.test_cases:
            self.test_cases[test_case.control_type].append(test_case)
        else:
            self.test_cases[test_case.control_type] = [test_case]

    async def execute(self, connection: Connection, controller: Controller):
        control_type = controller.control_type
        test_cases = self.test_cases.get(control_type, [])
        logger.info(self.test_cases)
        logger.info(
            "Executing test suite for %s control type. %s test cases to execute.",
            control_type,
            len(test_cases),
        )
        for TestCase in test_cases:
            control_type = TestCase.control_type
            test_case = TestCase(
                self.config.get_control_type_config(control_type),
                connection,
                controller,
                self.report,
            )
            await test_case.execute()


class TestSuiteBuilder:
    def __init__(self, config: ControlTypeTestConfig, report: ComplianceReport):
        self.test_suite = TestSuite(config, report)

    def with_test_case(self, test_case):
        self.test_suite.add_test_case(test_case)
        return self

    def build(self):
        return self.test_suite
