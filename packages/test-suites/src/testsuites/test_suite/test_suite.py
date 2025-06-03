import abc
import asyncio
from enum import Enum
import functools
import inspect
import logging
import time
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    ParamSpec,
    Tuple,
    Type,
    TypeVar,
)
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
from connectivity.channel import Channel
from testsuites.test_logger import (
    AbstractTestLogger,
    TestLogger,
    ServerTestLogger,
    TestLoggerLevel,
)

from connectivity.s2_channel import S2Channel

logger = logging.getLogger(__name__)


class NotApplicableTestException(Exception):
    """Raise in a test case if the situation has not arisen to properly test this."""


class PreconditionNotMet(Exception):
    """ "Raised when the preconditions of a test method haven't been met yet."""


class S2TestCase(unittest.TestCase):
    control_type: ProtocolControlType = ProtocolControlType.NO_SELECTION
    config: BaseTestConfig

    name: str

    test_logger: AbstractTestLogger

    TIMEOUT = 10

    # tests: List[Tuple[str, Callable, Tuple, Dict, TestResultStatus]]
    tests: asyncio.Queue[Tuple[str, Callable, Tuple, Dict, TestResultStatus]]

    # A list tuples containing a method and a int duration (seconds). Each trigger is called after the timeout of the previous one is complete.
    triggers: asyncio.Queue[
        Tuple[
            Callable[..., Awaitable] | None, int, Optional[asyncio.Event], Tuple, Dict
        ]
    ]

    controller: Controller
    config: BaseTestConfig

    # Mechanism to allow temporary replacement of controller handler methods with test ones.
    message_handlers: Dict[Type[S2Message], Callable[..., Awaitable[None]]] = {}
    original_handlers: Dict[Type[S2Message], Callable[..., Awaitable[None]]] = {}

    def __init__(
        self,
        config: BaseTestConfig,
        channel: S2Channel,
        controller: Controller,
        report: ComplianceReport,
        logger: AbstractTestLogger,
    ):
        super().__init__()
        self.channel = channel
        self.controller = controller
        self.config = config
        self.report = report

        try:
            if self.name is None:
                raise Exception()
        except:
            raise ValueError(
                f"Test case name must be declared as a constant for a test case class ({self.__class__})"
            )

        self.tests = asyncio.Queue()
        self.triggers = asyncio.Queue()
        self._triggers_complete_event = asyncio.Event()

        self.test_logger = logger

        self.test_logger.info(self.name, ident=0)

    async def add_test_method(
        self,
        name,
        method: Callable[..., Awaitable[None]],
        *args,
        fail_result_status=TestResultStatus.FAIL,
        **kwargs,
    ):
        """
        Add a test method to the list to be executed.
        This is either executed in the __init__ function or in a `generate_tests` function.
        In the init function we are adding static tests to our list of tests.
        In the generate function we are adding parametrized tests.

        Args:
            name (str): Name of the test for the report and logs
            method (Callable): A callable function that will tag the args and kwargs as parameters
            fail_result_status (TestResultStatus): The status that the result should get on fail. Should be either FAIL or SOFT_FAIL
        """

        await self.tests.put((name, method, args, kwargs, fail_result_status))
        # self.tests.append((name, method, args, kwargs, fail_result_status))

    async def add_trigger_method(
        self,
        method: Callable[..., Awaitable[None]] | None,
        *args,
        wait_time=30,
        event: Optional[asyncio.Event] = None,
        **kwargs,
    ):
        """The triggers are used to make events occur after a certain period of time.
        For example send an instruction and wait a certain period to see how the device reacts.
        The main test loop waits for the triggers task to complete and then exits.

        Args:
            method (Callable[..., Awaitable[None]] | None): _description_
            wait_time (int, optional): _description_. Defaults to 30.
        """
        await self.triggers.put((method, wait_time, event, args, kwargs))

    async def generate_tests(self):
        """
        This method is run just before the tests are to be executed.
        This can be used to generate parametrized test cases.
        Asynchronous tasks can be done/waited here in order to create the tests.
        """

        # Gather all the static tests and add them to the list of tests to be executed.
        # The tests generated at runtime are added during the execution
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if getattr(method, "_is_test_method", False):
                await self.add_test_method(method.test_name, method)  # type: ignore
    
    async def cleanup(self):
        pass

    def replace_controller_handlers(self):
        for k, v in self.message_handlers.items():
            if self.controller.handlers.get(k, None) is not None:
                self.original_handlers[k] = self.controller.handlers[k]
            self.controller.handlers[k] = v

    async def handle_with_original_handler(
        self, message: S2Message, channel: "S2Channel", send_okay: Awaitable
    ):
        if type(message) in self.original_handlers:
            await self.original_handlers[type(message)](message, channel, send_okay)

    def undo_controller_handler_replacement(self):
        for k, v in self.message_handlers.items():
            if self.original_handlers.get(k, None) is not None:
                self.controller.handlers[k] = self.original_handlers[k]
            elif k in self.controller.handlers:
                # If there wasn't a handler there before then we remove the key
                del self.controller.handlers[k]

    async def check_receive_message_type(
        self,
        message_type: Type[S2Message],
        timeout=None,
        not_applicable_if_not_received=False,
    ):
        """
        Checks the list of saved messages in the controller to see if a message of the specified type has arrived.
        If it hasn't arrived yet it will wait for it until the timeout is reached.

        Args:
            message_type (Type[S2Message]): The message type to retrieve
            not_applicable_if_not_received (bool): If true and no matching message found then a NotApplicableTestException raised.

        Returns:
            _type_: _description_
        """
        logger.info("Checking for %s", message_type)

        message = None
        timeout = self.TIMEOUT if timeout is None else timeout
        try:
            messages: list = self.controller.get_received_messages(message_type)
            if len(messages) < 1:
                message = await self.controller.message_awaiter.wait_for_message(
                    message_type, timeout
                )
            else:
                message = messages[0]
        except asyncio.TimeoutError:
            message = None

        if message is None:
            messages: list = self.controller.get_received_messages(message_type)
            if len(messages) > 0:
                message = messages[0]

        if message is None and not_applicable_if_not_received:
            raise NotApplicableTestException(
                f"No `{message_type.__name__}` received within {timeout} second timeout."
            )

        return message

    def handle_validation_error(self, err: S2ValidationError):
        # TODO: Use this...
        self.test_logger.error(f"Received validation error: {err}")

    @classmethod
    def test(cls, name=None):
        """
        Decorator which designates a method as a static test case.
        Used like: `@S2TestCase.test(name="Test Name")
        """

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

    async def triggers_task(self):
        try:
            while True:
                method, wait_time, event, args, kwargs = self.triggers.get_nowait()
                if method is not None:
                    await method(*args, **kwargs)

                if event is not None:
                    logger.info("Triggering task. Waiting until event set.")
                    await event.wait()
                    logger.info("Trigger complete.")
                else:
                    logger.info("Triggering task. Waiting %d seconds.", wait_time)
                    await asyncio.sleep(wait_time)
                    logger.info("Trigger complete.")
        except asyncio.QueueEmpty:
            pass
        finally:
            self._triggers_complete_event.set()

    async def run_test(
        self, name: str, method: Callable, args: tuple, kwargs: dict, fail_result_status
    ) -> TestResult:
        case_start_time = time.time()
        status = fail_result_status
        message: Optional[str] = None
        try:
            await self.setup()
            await method(*args, **kwargs)
            await self.teardown()

            self.test_logger.success(f"{name}")
            status = TestResultStatus.PASS
        except NotApplicableTestException as e:
            message = str(e)
            status = TestResultStatus.N_A
        except AssertionError as e:
            message = str(e)
            self.test_logger.error(f"Assertion error: {e}")
        except Exception as e:
            message = str(e)
            self.test_logger.error(f"Error: {e}")

        case_end_time = time.time()

        # Convert the test args to a dict to be added to the report.
        report_parameters = {
            **{f"arg_{index}": str(value) for index, value in enumerate(args)},
            **{key: str(value) for key, value in kwargs.items()},
        }
        if report_parameters == {}:
            report_parameters = None

        result = TestResult(
            name=name,
            status=status,
            duration=round(case_end_time - case_start_time, 2),
            message=message,
            parameters=report_parameters,
        )

        return result

    async def execute(self) -> TestSuiteResults:
        """Execute the tests from this test case and returns the result information for the report.

        Returns:
            TestSuiteResults: Result information.
        """

        # Control type set to the controller's control type since the NOT_CONTROLLABLE tests are run for each control type and could have different behaviors in each.
        test_suite_result = TestSuiteResults(
            name=self.name, control_type=self.controller.control_type
        )

        self._triggers_complete_event.clear()
        asyncio.create_task(self.triggers_task())

        if self.config.enabled:
            # Put any handlers in place
            self.replace_controller_handlers()
            start_time = time.time()

            # Generates the parametrized test cases and adds them to the tests list.
            # This method is overridden in subclasses for generating the test
            await self.generate_tests()

            logger.info("%s", self.name)

            tests_executed = 0

            # Now we run each test case that is in the tests list with the args provided.
            logger.info("Starting test case: %s", self.__class__.__name__)

            if self.triggers.empty():
                await self.add_trigger_method(None, 30)

            # Run the test loop until the triggers task is complete.
            while not self._triggers_complete_event.is_set():
                try:
                    name, method, args, kwargs, fail_result_status = (
                        await asyncio.wait_for(self.tests.get(), 1)
                    )

                    result = await self.run_test(
                        name, method, args, kwargs, fail_result_status
                    )

                    test_suite_result.add_test_result(result)
                    tests_executed += 1

                except asyncio.TimeoutError:
                    continue

            if tests_executed < 1:
                test_suite_result.status = TestResultStatus.N_A

            end_time = time.time()
            duration = round(end_time - start_time, 2)

            test_suite_result.duration = duration

            self.undo_controller_handler_replacement()
        else:
            self.test_logger.info("Skipping disabled test case.")
            test_suite_result.status = TestResultStatus.N_A
            test_suite_result.duration = None

        return test_suite_result


class TestSuite:
    config: RoleTestConfig
    test_cases: Dict[ProtocolControlType, List[Type[S2TestCase]]]
    report: ComplianceReport

    test_logger: AbstractTestLogger

    def __init__(
        self,
        config: RoleTestConfig,
        report: ComplianceReport,
        test_logger: AbstractTestLogger,
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
        try:
            # ! THIS AVOIDS A PASS BY REFERENCE. Otherwise the following list concatenation modifies the self.test_cases
            test_cases = self.test_cases[ProtocolControlType.NOT_CONTROLABLE].copy()
        except KeyError:
            test_cases = []

        if control_type != ProtocolControlType.NOT_CONTROLABLE:
            test_cases += self.test_cases.get(control_type, [])

        logger.info(
            "Executing test suite for %s control type. %s test cases to execute.",
            control_type,
            len(test_cases),
        )
        for TestCase in test_cases:
            config = self.config.get_control_type_config(role, TestCase.control_type)

            if config is None:
                raise ValueError("No config passed.")

            test_case = TestCase(
                config,  # type: ignore
                channel,
                controller,
                self.report,
                self.test_logger,
            )

            result = await test_case.execute()

            if result is not None:
                self.report.add_test_suite_result(result)


class TestSuiteBuilder:
    def __init__(
        self,
        config: RoleTestConfig,
        report: ComplianceReport,
        test_logger: AbstractTestLogger,
    ):
        self.test_suite = TestSuite(config, report, test_logger)

    def with_test_case(self, test_case):
        self.test_suite.add_test_case(test_case)
        return self

    def build(self):
        return self.test_suite
