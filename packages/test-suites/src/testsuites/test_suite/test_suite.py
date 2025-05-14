import abc
import asyncio
import functools
import inspect
import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Type

from testsuites.certificate.certificate import (
    ComplianceFinding,
    ComplianceParameter,
    ComplianceReport,
    ComplianceStatus,
)
from connectivity.config import BaseTestConfig, ControlTypeTestConfig
from testsuites.controllers.controller import Controller
from s2python.common import ControlType as ProtocolControlType
from s2python.message import S2Message
from s2python.s2_validation_error import S2ValidationError

from connectivity.s2_channel import S2Channel

logger = logging.getLogger(__name__)


class TestLogger:

    logger: logging.Logger

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def info(self, message, ident=2):
        self.logger.info("%s[INFO] %s", " " * ident, message)

    def success(self, message, ident=2):
        self.logger.info("%s[SUCCESS] %s", " " * ident, message)

    def soft_error(self, message, ident=2):
        self.logger.warning("%s[SOFT-FAIL] %s", " " * ident, message)

    def error(self, message, ident=2):
        self.logger.warning("%s[FAIL] %s", " " * ident, message)

    def log(self, message, status: ComplianceStatus = ComplianceStatus.PASS, ident=2):
        match status:
            case ComplianceStatus.PASS:
                self.success(message, ident=ident)
            case ComplianceStatus.SOFT_FAIL:
                self.soft_error(message, ident=ident)
            case ComplianceStatus.FAIL:
                self.error(message, ident=ident)

    def log_status_list(self, message, statuses: list[ComplianceStatus], ident=2):
        if ComplianceStatus.FAIL in statuses:
            self.error(message, ident=ident)
        elif ComplianceStatus.SOFT_FAIL in statuses:
            self.soft_error(message, ident=ident)
        elif ComplianceStatus.PASS in statuses:
            self.success(message, ident=ident)


class S2TestCase(abc.ABC):
    control_type: ProtocolControlType = ProtocolControlType.NO_SELECTION
    config: BaseTestConfig

    finding: ComplianceFinding

    test_logger: TestLogger

    TIMEOUT = 5

    def __init__(
        self,
        config: BaseTestConfig,
        channel: S2Channel,
        controller: Controller,
        report: ComplianceReport,
        logger: TestLogger,
    ):
        self.channel = channel
        self.controller = controller
        self.config = config
        self.report = report

        finding_set = True
        try:
            if self.finding is None:
                finding_set = False
        except:
            finding_set = False

        if not finding_set:
            raise ValueError(
                "Finding must be declared as a constant for a test case class."
            )

        self.test_logger = logger

        self.test_logger.info(self.finding.test, ident=0)

    def add_finding_param(
        self,
        name: str,
        detail: Optional[str] = None,
        status: ComplianceStatus = ComplianceStatus.PASS,
    ):
        param = ComplianceParameter(name=name, detail=detail, status=status)

        self.finding.add_parameter(param=param)

    async def check_receive_message_type(
        self,
        message_type: Type[S2Message],
    ):
        logger.info("Checking for %s", message_type)

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
            self.add_finding_param(
                name=f"{message_type.__name__} Provided.",
                status=ComplianceStatus.PASS,
            )
        else:
            self.add_finding_param(
                name=f"{message_type.__name__} Not Provided.",
                status=ComplianceStatus.FAIL,
            )

        return message

    def handle_validation_error(self, err: S2ValidationError):
        self.test_logger.error(f"Received validation error: {err}")
        pass

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
            len(self.get_test_cases()),
        )
        for name, method in self.get_test_cases():
            # self.logger.info(f"Running test case: {name}")
            await self.setup()
            try:
                await method()
            finally:
                await self.teardown()
        # self.logger.info("Test case %s complete.", self.__class__.__name__)
        # self.logger.info("-" * 20)


class TestSuite:
    config: ControlTypeTestConfig
    test_cases: Dict[ProtocolControlType, List[Type[S2TestCase]]]
    report: ComplianceReport

    test_logger: TestLogger

    def __init__(
        self,
        config: ControlTypeTestConfig,
        report: ComplianceReport,
        test_logger: TestLogger,
    ):
        self.test_cases = {}
        self.config = config
        self.report = report

        self.test_logger = test_logger

    def add_test_case(self, test_case: Type[S2TestCase]):
        if test_case.control_type in self.test_cases:
            self.test_cases[test_case.control_type].append(test_case)
        else:
            self.test_cases[test_case.control_type] = [test_case]

    async def execute(self, channel: S2Channel, controller: Controller):
        control_type = controller.control_type
        test_cases = self.test_cases.get(ProtocolControlType.NO_SELECTION, [])
        test_cases += self.test_cases.get(control_type, [])

        logger.info(
            "Executing test suite for %s control type. %s test cases to execute.",
            control_type,
            len(test_cases),
        )
        for TestCase in test_cases:
            control_type = TestCase.control_type
            test_case = TestCase(
                self.config.get_control_type_config(control_type),
                channel,
                controller,
                self.report,
                self.test_logger,
            )
            await test_case.execute()

            self.report.add_finding(test_case.finding)


class TestSuiteBuilder:
    def __init__(
        self,
        config: ControlTypeTestConfig,
        report: ComplianceReport,
        test_logger: TestLogger,
    ):
        self.test_suite = TestSuite(config, report, test_logger)

    def with_test_case(self, test_case):
        self.test_suite.add_test_case(test_case)
        return self

    def build(self):
        return self.test_suite
