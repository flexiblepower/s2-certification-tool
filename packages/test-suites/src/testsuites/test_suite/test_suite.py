import abc
import asyncio
import functools
import inspect
import logging
import time
from typing import TYPE_CHECKING, Callable, Coroutine, Dict, List, Optional, Tuple, Type
import unittest

from testsuites.certificate.certificate import (
    TestSuiteResults,
    TestResult,
    ComplianceReport,
    TestResultStatus,
)
from connectivity.config import BaseTestConfig, ControlTypeRMTestConfig, RoleTestConfig
from testsuites.controllers.controller import Controller
from s2python.common import ControlType as ProtocolControlType, EnergyManagementRole
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

    def log(self, message, status: TestResultStatus = TestResultStatus.PASS, ident=2):
        match status:
            case TestResultStatus.PASS:
                self.success(message, ident=ident)
            case TestResultStatus.SOFT_FAIL:
                self.soft_error(message, ident=ident)
            case TestResultStatus.FAIL:
                self.error(message, ident=ident)

    def log_status_list(self, message, statuses: list[TestResultStatus], ident=2):
        if TestResultStatus.FAIL in statuses:
            self.error(message, ident=ident)
        elif TestResultStatus.SOFT_FAIL in statuses:
            self.soft_error(message, ident=ident)
        elif TestResultStatus.PASS in statuses:
            self.success(message, ident=ident)


class S2TestCase(unittest.TestCase):
    control_type: ProtocolControlType = ProtocolControlType.NO_SELECTION
    config: BaseTestConfig

    name: str

    test_logger: TestLogger

    TIMEOUT = 5

    tests: List[Tuple[str, Callable, Tuple, Dict]]

    def __init__(
        self,
        config: BaseTestConfig,
        channel: S2Channel,
        controller: Controller,
        report: ComplianceReport,
        logger1: TestLogger,
    ):
        super().__init__()
        self.channel = channel
        self.controller = controller
        self.config = config
        self.report = report

        name_set = True
        try:
            if self.name is None:
                name_set = False
        except:
            name_set = False

        if not name_set:
            raise ValueError(
                f"Test case name must be declared as a constant for a test case class ({self.__class__})"
            )

        self.tests: List[Tuple[str, Callable, Tuple, Dict, TestResultStatus]] = []
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if getattr(method, "_is_test_method", False):
                self.add_test_method(method.test_name, method)  # type: ignore

        self.test_logger = logger1

        self.test_logger.info(self.name, ident=0)

    def add_test_method(
        self,
        name,
        method: Callable,
        *args,
        fail_result_status=TestResultStatus.FAIL,
        **kwargs,
    ):
        self.tests.append((name, method, args, kwargs, fail_result_status))

    async def generate_tests(self):
        pass

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

        return message

    def handle_validation_error(self, err: S2ValidationError):
        self.test_logger.error(f"Received validation error: {err}")
        pass

    @classmethod
    def test(cls, name=None):
        def decorator(func):
            func._is_test_method = True
            if name is not None:
                func.test_name = name
            else:
                func.test_name = func.__name__
            return func

        return decorator

    async def setup(self):
        """Override in subclass for per-test setup."""
        pass

    async def teardown(self):
        """Override in subclass for per-test teardown."""
        pass

    async def execute(self) -> TestSuiteResults:
        # logger.info(
        #     "Executing test case %s. Has %s tests.",
        #     self.__class__.__name__,
        #     len(self.tests),
        # )
        test_suite_result = TestSuiteResults(name=self.name)
        start_time = time.time()

        # Generates the parametarised test cases and adds them to the tests list.
        # This method is overridden in subclasses for generating the test
        await self.generate_tests()

        logger.info("%s: %s", self.name, len(self.tests))

        for name, method, args, kwargs, fail_result_status in self.tests:
            case_start_time = time.time()
            status = fail_result_status
            message: Optional[str] = None
            try:
                await self.setup()
                try:
                    await method(*args, **kwargs)
                finally:
                    await self.teardown()

                self.test_logger.success(f"{name}")
                status = TestResultStatus.PASS
            except AssertionError as e:
                message = str(e)
                self.test_logger.error(f"Assertion error: {e}")
                # self.report.add_test_suite_result(f"{name}: FAILED ({e})")
            except Exception as e:
                message = str(e)
                self.test_logger.error(f"Error error: {e}")

            case_end_time = time.time()

            result = TestResult(
                name=name,
                status=status,
                duration=round(case_end_time - case_start_time, 2),
                message=message,
                parameters={
                    **{f"arg_{index}": str(value) for index, value in enumerate(args)},
                    **{key: str(value) for key, value in kwargs.items()},
                },
            )

            test_suite_result.add_test_result(result)

        if len(self.tests) < 1:
            test_suite_result.status = TestResultStatus.N_A

        end_time = time.time()
        duration = round(end_time - start_time, 2)

        test_suite_result.duration = duration
        # self.logger.info("Test case %s complete.", self.__class__.__name__)
        # self.logger.info("-" * 20)

        return test_suite_result


class TestSuite:
    config: RoleTestConfig
    test_cases: Dict[ProtocolControlType, List[Type[S2TestCase]]]
    report: ComplianceReport

    test_logger: TestLogger

    def __init__(
        self,
        config: RoleTestConfig,
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

    async def execute(
        self, channel: S2Channel, controller: Controller, role: EnergyManagementRole
    ):
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
                self.config.get_control_type_config(role, control_type),
                channel,
                controller,
                self.report,
                self.test_logger,
            )

            result = await test_case.execute()

            self.report.add_test_suite_result(result)


class TestSuiteBuilder:
    def __init__(
        self,
        config: RoleTestConfig,
        report: ComplianceReport,
        test_logger: TestLogger,
    ):
        self.test_suite = TestSuite(config, report, test_logger)

    def with_test_case(self, test_case):
        self.test_suite.add_test_case(test_case)
        return self

    def build(self):
        return self.test_suite
