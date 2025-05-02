import abc
import asyncio
import functools
import inspect
import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Type

from s2testing.certificate.certificate import (
    ComplianceFinding,
    ComplianceParameter,
    ComplianceReport,
    ComplianceStatus,
)
from s2testing.config import BaseTestConfig, ControlTypeTestConfig
from s2testing.connection import BaseRMConnection
from s2testing.controllers.controller import Controller
from s2python.common import ControlType as ProtocolControlType
from s2python.message import S2Message

logger = logging.getLogger(__name__)


class S2TestCase(abc.ABC):
    control_type: ProtocolControlType = ProtocolControlType.NO_SELECTION
    config: BaseTestConfig

    TIMEOUT = 5

    def __init__(
        self,
        config: BaseTestConfig,
        connection: BaseRMConnection,
        controller: Controller,
        report: ComplianceReport,
    ):
        self.connection = connection
        self.controller = controller
        self.config = config
        self.report = report

    async def check_receive_message_type(
        self,
        message_type: Type[S2Message],
        report_finding: Optional[ComplianceFinding] = None,
    ):
        logger.info("Checking for %s", message_type)

        if report_finding is None:
            report_finding = ComplianceFinding(message_type=message_type)

        message = None
        try:
            messages: list = self.controller.get_received_messages(message_type)
            if len(messages) < 1:
                message = await self.controller.message_awaiter.wait_for_message(
                    message_type, self.TIMEOUT
                )
            else:
                message = messages[0]
        except asyncio.TimeoutError:
            message = None

        if message is None:
            messages: list = self.controller.get_received_messages(message_type)
            if len(messages) > 0:
                message = messages[0]

        if message is not None:
            report_finding.add_parameter(
                name=f"{message_type.__name__} Provided.",
                status=ComplianceStatus.PASS,
            )
        else:
            report_finding.add_parameter(
                name=f"{message_type.__name__} Not Provided.",
                status=ComplianceStatus.FAIL,
            )

        return message

    @classmethod
    def test(cls, func):
        func._is_test_case = True
        return func

    async def setup(self):
        """Override in subclass for per-test setup."""
        pass

    async def teardown(self):
        """Override in subclass for per-test teardown."""
        pass

    def get_test_cases(self):
        test_cases = []
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if getattr(method, "_is_test_case", False):
                test_cases.append((name, method))
        return test_cases

    async def execute(self):
        logger.info(
            "Executing test case %s. Has %s tests.",
            self.__class__.__name__,
            self.get_test_cases(),
        )
        for name, method in self.get_test_cases():
            logger.info(f"Running test case: {name}")
            await self.setup()
            try:
                await method()
            finally:
                await self.teardown()
        logger.info("Test case %s complete.", self.__class__.__name__)


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

    async def execute(self, connection: BaseRMConnection, controller: Controller):
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
